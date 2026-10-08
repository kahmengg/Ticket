import logging
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from urllib.parse import urlencode

import requests
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.models import Alert, Event
from app.services.watchlist import WatchMatch, matched_watchlists_for_event
from app.services.sale_windows import ReminderSale, reminder_sales
from app.services.telegram_payload import message_payload
from app.services.event_presentation import status_text

logger = logging.getLogger(__name__)


def telegram_api_call(method: str, payload: dict):
    if not settings.telegram_bot_token:
        return None
    try:
        response = requests.post(f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}",
                                 json=payload, timeout=10)
        data = response.json()
        # Repeated button taps may legitimately request an identical message.
        if method.startswith("editMessage") and "message is not modified" in str(data.get("description", "")).lower():
            return True
        if response.ok and data.get("ok"):
            return data.get("result", True)
    except (requests.RequestException, ValueError):
        pass
    logger.warning("Telegram %s failed.", method)
    return None


def queue_event_alerts(events: list[Event], alert_type: str, db: Session) -> None:
    for event in events:
        key = "new_event" if alert_type == "new_event" else f"event_updated:r{event.revision}"
        for chat_id in get_notification_chat_ids(db):
            _queue_alert(db, event, key, chat_id, format_event_message(event, alert_type))


def _queue_alert(db: Session, event: Event, key: str, chat_id: str, message: str, sale_date=None) -> None:
    if crud.alert_exists(db, event.id, key, chat_id):
        return
    # A savepoint lets a concurrent insert lose cleanly without rolling back event changes.
    try:
        with db.begin_nested():
            db.add(Alert(event_id=event.id, chat_id=chat_id, alert_type=key,
                         message=message, delivery_state="pending", sale_date=sale_date))
            db.flush()
    except IntegrityError:
        if not crud.alert_exists(db, event.id, key, chat_id):
            raise


def send_event_alerts(events: list[Event], alert_type: str, db: Session | None = None) -> int:
    if db is None:
        return sum(send_telegram_message(format_event_message(event, alert_type)) for event in events)
    queue_event_alerts(events, alert_type, db)
    db.commit()
    return deliver_pending_alerts(db)


def send_new_event_alerts(events: list[Event], db: Session | None = None) -> int:
    return send_event_alerts(events, "new_event", db)


def send_updated_event_alerts(events: list[Event], db: Session | None = None) -> int:
    return send_event_alerts(events, "event_updated", db)


def send_sale_reminder_alerts(matches: list[WatchMatch], reminder_hours: int, db: Session) -> int:
    for match in matches:
        if crud.telegram_subscription_state(db, match.chat_id) is not True:
            continue
        event = match.event
        sale = match.sale or (ReminderSale("general", "General sale", event.sale_date, "general") if event.sale_date else None)
        if event.id is None or sale is None or event.status in {"cancelled", "postponed"}:
            continue
        sale_date = _utc(sale.starts_at)
        key = sale.key(reminder_hours)
        # A delayed run inside the short window should send one timely reminder, not both.
        if reminder_hours > 1 and sale_date <= datetime.now(timezone.utc) + timedelta(hours=1):
            continue
        _queue_alert(db, event, key, match.chat_id,
                     format_sale_reminder_message(event, match.keyword, reminder_hours, sale), sale_date)
    db.commit()
    return deliver_pending_alerts(db)


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def claim_alert(db: Session, alert_id: int, now) -> str | None:
    token = str(uuid4())
    # An atomic compare-and-update allows only one worker to own a live delivery lease.
    claimed = db.execute(update(Alert).execution_options(synchronize_session=False).where(
        Alert.id == alert_id, Alert.delivery_state.in_(["pending", "sending"]),
        or_(Alert.next_attempt_at.is_(None), Alert.next_attempt_at <= now),
    ).values(delivery_state="sending", lease_token=token,
             next_attempt_at=now + timedelta(minutes=5), attempts=Alert.attempts + 1))
    db.commit()
    return token if claimed.rowcount == 1 else None


def deliver_pending_alerts(db: Session, now=None, limit: int = 100) -> int:
    if not settings.telegram_bot_token:
        return 0
    query_time = now or datetime.now(timezone.utc)
    ids = list(db.scalars(select(Alert.id).where(
        Alert.delivery_state.in_(["pending", "sending"]),
        or_(Alert.next_attempt_at.is_(None), Alert.next_attempt_at <= query_time),
    ).order_by(Alert.id).limit(limit)))
    sent = 0
    for alert_id in ids:
        # Refresh the clock per message: a large batch can outlast a delivery lease.
        delivery_time = now or datetime.now(timezone.utc)
        token = claim_alert(db, alert_id, delivery_time)
        if token is None:
            continue
        alert = db.get(Alert, alert_id, populate_existing=True)
        event = db.get(Event, alert.event_id, populate_existing=True)
        active = crud.telegram_subscription_state(db, alert.chat_id)
        cancelled = active is False
        if alert.sale_date is not None:
            # Recheck expiry, rescheduling and /unwatch after a failed or delayed send.
            cancelled = cancelled or active is not True
            cancelled = cancelled or event.status in {"cancelled", "postponed"}
            cancelled = cancelled or _utc(alert.sale_date) <= delivery_time
            hours = int(alert.alert_type.split("_reminder_", 1)[1].split("h:", 1)[0])
            cancelled = cancelled or not any(sale.key(hours) == alert.alert_type for sale in reminder_sales(event))
            cancelled = cancelled or not any(
                watch.chat_id == alert.chat_id for watch in matched_watchlists_for_event(db, event)
            )
        if cancelled:
            state, sent_at, retry_at = "cancelled", None, None
        else:
            delivered = send_telegram_message_to_chat(alert.chat_id, alert.message)
            if delivered is None:
                state, sent_at, retry_at = "failed", None, None
            else:
                if delivered:
                    state, sent_at, retry_at = "sent", datetime.now(timezone.utc), None
                    sent += 1
                else:
                    state, sent_at = "pending", None
                    retry_at = delivery_time + timedelta(minutes=min(60, 2 ** min(alert.attempts, 6)))
        db.execute(update(Alert).where(Alert.id == alert_id, Alert.lease_token == token).values(
            delivery_state=state, sent_at=sent_at, next_attempt_at=retry_at, lease_token=None,
        ))
        db.commit()
    return sent


def send_telegram_message(message: str, chat_ids: list[str] | None = None) -> int:
    target_chat_ids = get_notification_chat_ids() if chat_ids is None else chat_ids
    if not settings.telegram_bot_token or not target_chat_ids:
        return 0

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    sent_count = 0
    for chat_id in target_chat_ids:
        if _send_telegram_message_to_chat(url, chat_id, message):
            sent_count += 1
    return sent_count


def send_telegram_message_to_chat(chat_id: str, message: str) -> bool | None:
    if not settings.telegram_bot_token:
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    return _send_telegram_message_to_chat(url, chat_id, message)


def get_notification_chat_ids(db: Session | None = None) -> list[str]:
    chat_ids = list(settings.telegram_chat_ids)
    if db is not None:
        chat_ids.extend(crud.list_active_telegram_chat_ids(db))
        chat_ids = [chat_id for chat_id in chat_ids if crud.telegram_subscription_state(db, chat_id) is not False]
    return list(dict.fromkeys(chat_ids))


def _send_telegram_message_to_chat(url: str, chat_id: str, message: str) -> bool | None:
    try:
        response = requests.post(
            url,
            json=message_payload(chat_id, message),
            timeout=10,
        )
        if response.status_code in {400, 403, 404}:
            logger.warning("Telegram permanently rejected delivery (HTTP %s).", response.status_code)
            # None marks a permanent rejection; False remains retryable.
            return None
        response.raise_for_status()
        return True
    except requests.RequestException:
        logger.warning("Telegram delivery failed; notification remains eligible for retry.")
        return False


def format_event_message(event: Event, alert_type: str = "new_event", now=None) -> str:
    now = now or datetime.now(timezone.utc)
    title = _clean_event_title(event.title)
    lines = ["Concert found", title]
    if alert_type == "event_updated":
        lines[0] = "Event details updated"
        if getattr(event, "changed_fields", None):
            lines.append("Changed: " + ", ".join(event.changed_fields))
    if event.venue_name:
        lines.append(f"Venue: {event.venue_name}")
    if event.event_date:
        lines.append(f"Event date: {_format_datetime(event.event_date)}")
    if event.sale_date:
        label = "General sale started" if _utc(event.sale_date) <= now else "General sale opens"
        lines.append(f"{label}: {_format_datetime(event.sale_date)}")
    if event.presale_date:
        label = "Presale started" if _utc(event.presale_date) <= now else "Presale opens"
        lines.append(f"{label}: {_format_datetime(event.presale_date)}")
    if event.price_summary:
        lines.append(f"Prices: {event.price_summary}")
    if event.status in {"cancelled", "postponed", "sold_out", "unavailable"}:
        lines.append(f"Status: {status_text(event, now)}")
    lines.append(f"URL: {event.url}")
    lines.extend(_additional_source_links(event))
    concert_calendar_url = _google_calendar_url(
        title=_clean_event_title(event.title),
        start=event.event_date,
        duration=timedelta(hours=3),
        details=event.url,
        location=event.venue_name,
    )
    if concert_calendar_url and _utc(event.event_date) > now and event.status not in {"cancelled", "postponed"}:
        lines.append(f"Add concert to calendar: {concert_calendar_url}")
    sale_calendar_url = _google_calendar_url(
        title=f"Ticket sale: {_clean_event_title(event.title)}",
        start=event.sale_date,
        duration=timedelta(minutes=30),
        details=event.url,
        location=event.venue_name,
    )
    if sale_calendar_url and _utc(event.sale_date) > now and event.status not in {"cancelled", "postponed"}:
        lines.append(f"Add ticket sale to calendar: {sale_calendar_url}")
    return "\n".join(lines)


def format_sale_reminder_message(event: Event, keyword: str, reminder_hours: int, sale=None) -> str:
    hours_text = "1 hour" if reminder_hours == 1 else f"{reminder_hours} hours"
    lines = [
        f"Reminder: {sale.name if sale else 'ticket sale'} starts within {hours_text}",
        f"Watchlist: {keyword}",
        _clean_event_title(event.title),
    ]
    if event.venue_name:
        lines.append(f"Venue: {event.venue_name}")
    reminder_date = sale.starts_at if sale else event.sale_date
    if reminder_date:
        lines.append(f"Sale date: {_format_datetime(reminder_date)}")
    if event.event_date:
        lines.append(f"Event date: {_format_datetime(event.event_date)}")
    if event.price_summary:
        lines.append(f"Prices: {event.price_summary}")
    if event.status in {"cancelled", "postponed", "sold_out", "unavailable"}:
        lines.append(f"Status: {status_text(event)}")
    lines.append(f"URL: {event.url}")
    lines.extend(_additional_source_links(event))
    sale_calendar_url = _google_calendar_url(
        title=f"Ticket sale: {_clean_event_title(event.title)}",
        start=reminder_date,
        duration=timedelta(minutes=30),
        details=event.url,
        location=event.venue_name,
    )
    if sale_calendar_url:
        lines.append(f"Add ticket sale to calendar: {sale_calendar_url}")
    concert_calendar_url = _google_calendar_url(
        title=_clean_event_title(event.title),
        start=event.event_date,
        duration=timedelta(hours=3),
        details=event.url,
        location=event.venue_name,
    )
    if concert_calendar_url:
        lines.append(f"Add concert to calendar: {concert_calendar_url}")
    return "\n".join(lines)


def _additional_source_links(event: Event) -> list[str]:
    # Retain the canonical URL while offering links to the other providers.
    seen = {event.url}
    lines = []
    for listing in sorted(event.listings, key=lambda item: item.source_name):
        if listing.url not in seen:
            lines.append(f"{listing.source_name}: {listing.url}")
            seen.add(listing.url)
    return lines


def _clean_event_title(title: str) -> str:
    return re.sub(r"^\s*20\d{2}(?:\s*[-/]\s*\d{2,4})?\s+", "", title).strip()


def _format_datetime(value) -> str:
    return _utc(value).astimezone(timezone(timedelta(hours=8))).strftime("%d %b %Y, %I:%M %p SGT")


def _google_calendar_url(
    title: str,
    start,
    duration: timedelta,
    details: str,
    location: str | None = None,
) -> str | None:
    if not start:
        return None

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = start + duration

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": f"{start.strftime('%Y%m%dT%H%M%SZ')}/{end.strftime('%Y%m%dT%H%M%SZ')}",
        "details": details,
    }
    if location:
        params["location"] = location
    return f"https://calendar.google.com/calendar/render?{urlencode(params)}"
