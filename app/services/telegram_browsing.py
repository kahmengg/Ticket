"""Small, signed, stateless Telegram catalogue pages."""
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import re
from urllib.parse import urlsplit

from app import crud
from app.services.notifications import _format_datetime, telegram_api_call

TTL = 24 * 60 * 60


def _signature(payload, chat_id, message_id, secret):
    raw = f"{chat_id}:{message_id}:{payload}".encode()
    return base64.urlsafe_b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()[:12]).decode().rstrip("=")


def button_data(kind, page, cutoff, chat_id, message_id, secret):
    payload = f"pg:{'l' if kind == 'latest' else 'u'}:{page}:{cutoff}"
    return f"{payload}:{_signature(payload, chat_id, message_id, secret)}"


def read_button(data, chat_id, message_id, secret, now):
    if not isinstance(data, str) or len(data.encode()) > 64 or not secret:
        raise ValueError("Invalid controls. Send /latest or /upcoming again.")
    match = re.fullmatch(r"(pg:([lu]):(r|\d{1,8}):(\d{1,12})):([A-Za-z0-9_-]{16})", data)
    if not match or not hmac.compare_digest(match[5], _signature(match[1], chat_id, message_id, secret)):
        raise ValueError("Invalid controls. Send /latest or /upcoming again.")
    cutoff = int(match[4])
    if cutoff > now + 5 or now - cutoff >= TTL:
        raise ValueError("These controls expired. Send /latest or /upcoming again.")
    return ("latest" if match[2] == "l" else "upcoming", match[3], cutoff)


def _clip(value, limit):
    text = " ".join(str(value or "").split())
    # Count UTF-16 units so emoji cannot overflow Telegram's message limit.
    while len(text.encode("utf-16-le")) // 2 > limit:
        text = text[:-1]
    return text


def page_content(db, kind, page, cutoff, now):
    events, total, page, pages = crud.browse_events(db, kind, now,
        datetime.fromtimestamp(cutoff, timezone.utc), page)
    text = f"{'Latest concerts found' if kind == 'latest' else 'Upcoming concerts'}\nPage {page + 1} of {pages} · {total} concerts"
    entities = []
    previous_group = None
    for index, event in enumerate(events, start=page * 5 + 1):
        if kind == "latest":
            group = "New discoveries" if event.discovery_kind == "discovered" else "Previously imported"
            if group != previous_group:
                text += f"\n\n{group}"
                previous_group = group
        text += f"\n\n{index}. {_clip(event.title, 140)}"
        for label, value in (("Venue", _clip(event.venue_name, 80)),
                             ("Event date", _format_datetime(event.event_date) if event.event_date else "Date to be confirmed"),
                             ("Sale date", _format_datetime(event.sale_date) if event.sale_date else None),
                             ("Prices", _clip(event.price_summary, 70)),
                             ("Status", (event.status or "").replace("_", " "))):
            if value:
                text += f"\n{label}: {value}"
        if kind == "latest" and event.discovery_kind == "discovered" and event.discovered_at:
            text += f"\nFound: {_format_datetime(event.discovered_at)}"
        if urlsplit(event.url).scheme in {"https", "http"}:
            text += "\n"
            # Link entities preserve complete URLs without spending message characters on long URLs.
            entities.append(dict(type="text_link", offset=len(text.encode("utf-16-le")) // 2,
                                 length=7, url=event.url))
            text += "Tickets"
    if not events:
        text += "\n\nNo concerts found yet."
    return dict(text=text, entities=entities, link_preview_options={"is_disabled": True}), page, pages


def keyboard(kind, page, pages, cutoff, chat_id, message_id, secret):
    navigation = []
    for label, target in (("Previous", page - 1), ("Next", page + 1)):
        if 0 <= target < pages:
            navigation.append(dict(text=label, callback_data=button_data(kind, target, cutoff, chat_id, message_id, secret)))
    rows = [navigation] if navigation else []
    rows.append([dict(text="Refresh", callback_data=button_data(kind, "r", cutoff, chat_id, message_id, secret))])
    return {"inline_keyboard": rows}


def send_browse_page(db, kind, chat_id, secret, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = int(now.timestamp())
    content, page, pages = page_content(db, kind, 0, cutoff, now)
    response = telegram_api_call("sendMessage", dict(chat_id=chat_id, **content))
    message_id = response.get("message_id") if isinstance(response, dict) else None
    if message_id is None:
        return False
    # Telegram assigns the message ID on send, so attach message-bound controls afterwards.
    return telegram_api_call("editMessageReplyMarkup", dict(chat_id=chat_id, message_id=message_id,
        reply_markup=keyboard(kind, page, pages, cutoff, chat_id, message_id, secret))) is not None


def handle_browse_callback(db, query, secret, now=None):
    now = now or datetime.now(timezone.utc)
    callback_id = query.get("id")
    if not isinstance(callback_id, str):
        return False
    message = query.get("message") or {}
    try:
        chat_id, message_id = message["chat"]["id"], message["message_id"]
        kind, target, cutoff = read_button(query.get("data"), chat_id, message_id, secret, int(now.timestamp()))
    except (ValueError, KeyError, TypeError) as exc:
        note = str(exc) if isinstance(exc, ValueError) else "Send /latest or /upcoming again."
        telegram_api_call("answerCallbackQuery", dict(callback_query_id=callback_id, text=note))
        return False
    telegram_api_call("answerCallbackQuery", dict(callback_query_id=callback_id))
    if target == "r":
        cutoff, target = int(now.timestamp()), 0
    content, page, pages = page_content(db, kind, int(target), cutoff, now)
    edited = telegram_api_call("editMessageText", dict(chat_id=chat_id, message_id=message_id, **content,
        reply_markup=keyboard(kind, page, pages, cutoff, chat_id, message_id, secret)))
    if edited is None:
        telegram_api_call("answerCallbackQuery", dict(callback_query_id=callback_id,
            text="Could not update this message. Please send the command again."))
    return edited is not None
