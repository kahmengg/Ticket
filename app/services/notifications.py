import logging
import re
from datetime import timedelta, timezone
from urllib.parse import urlencode

import requests
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.models import Event
from app.services.watchlist import WatchMatch

logger = logging.getLogger(__name__)


def send_event_alerts(events: list[Event], alert_type: str, db: Session | None = None) -> int:
    chat_ids = get_notification_chat_ids(db)
    if not settings.telegram_bot_token or not chat_ids:
        logger.info("Telegram credentials are missing; skipping notifications.")
        return 0

    sent_count = 0
    for event in events:
        message = format_event_message(event, alert_type=alert_type)
        for chat_id in chat_ids:
            if db is not None and event.id is not None and crud.alert_exists(db, event.id, alert_type, chat_id):
                continue
            if send_telegram_message_to_chat(chat_id, message):
                sent_count += 1
                if db is not None and event.id is not None:
                    crud.create_alert(db, event.id, alert_type, chat_id, message)
    if db is not None:
        db.commit()
    return sent_count


def send_new_event_alerts(events: list[Event], db: Session | None = None) -> int:
    return send_event_alerts(events, "new_event", db)


def send_updated_event_alerts(events: list[Event], db: Session | None = None) -> int:
    return send_event_alerts(events, "event_updated", db)


def send_sale_reminder_alerts(matches: list[WatchMatch], reminder_hours: int, db: Session) -> int:
    if not settings.telegram_bot_token:
        logger.info("Telegram credentials are missing; skipping sale reminders.")
        return 0

    sent_count = 0
    alert_type = f"sale_reminder_{reminder_hours}h"
    for match in matches:
        event = match.event
        if event.id is None or crud.alert_exists(db, event.id, alert_type, match.chat_id):
            continue
        message = format_sale_reminder_message(event, match.keyword, reminder_hours)
        if send_telegram_message_to_chat(match.chat_id, message):
            sent_count += 1
            crud.create_alert(db, event.id, alert_type, match.chat_id, message)
    db.commit()
    return sent_count


def send_telegram_message(message: str, chat_ids: list[str] | None = None) -> int:
    target_chat_ids = chat_ids or get_notification_chat_ids()
    if not settings.telegram_bot_token or not target_chat_ids:
        return 0

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    sent_count = 0
    for chat_id in target_chat_ids:
        if _send_telegram_message_to_chat(url, chat_id, message):
            sent_count += 1
    return sent_count


def send_telegram_message_to_chat(chat_id: str, message: str) -> bool:
    if not settings.telegram_bot_token:
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    return _send_telegram_message_to_chat(url, chat_id, message)


def get_notification_chat_ids(db: Session | None = None) -> list[str]:
    chat_ids = list(settings.telegram_chat_ids)
    if db is not None:
        chat_ids.extend(crud.list_active_telegram_chat_ids(db))
    return list(dict.fromkeys(chat_ids))


def _send_telegram_message_to_chat(url: str, chat_id: str, message: str) -> bool:
    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "disable_web_page_preview": False},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException:
        logger.exception("Failed to send Telegram notification to chat_id=%s.", chat_id)
        return False


def format_event_message(event: Event, alert_type: str = "new_event") -> str:
    title = _clean_event_title(event.title)
    lines = [title]
    if alert_type == "event_updated":
        lines.insert(0, "Event details updated")
    if event.venue_name:
        lines.append(f"Venue: {event.venue_name}")
    if event.event_date:
        lines.append(f"Event date: {_format_datetime(event.event_date)}")
    if event.sale_date:
        lines.append(f"Sale date: {_format_datetime(event.sale_date)}")
    if event.presale_date:
        lines.append(f"Presale date: {_format_datetime(event.presale_date)}")
    lines.append(f"URL: {event.url}")
    calendar_url = _google_calendar_url(event)
    if calendar_url:
        lines.append(f"Add to calendar: {calendar_url}")
    return "\n".join(lines)


def format_sale_reminder_message(event: Event, keyword: str, reminder_hours: int) -> str:
    hours_text = "1 hour" if reminder_hours == 1 else f"{reminder_hours} hours"
    lines = [
        f"Reminder: ticket sale starts within {hours_text}",
        f"Watchlist: {keyword}",
        _clean_event_title(event.title),
    ]
    if event.venue_name:
        lines.append(f"Venue: {event.venue_name}")
    if event.sale_date:
        lines.append(f"Sale date: {_format_datetime(event.sale_date)}")
    if event.event_date:
        lines.append(f"Event date: {_format_datetime(event.event_date)}")
    lines.append(f"URL: {event.url}")
    calendar_url = _google_calendar_url(event)
    if calendar_url:
        lines.append(f"Add to calendar: {calendar_url}")
    return "\n".join(lines)


def _clean_event_title(title: str) -> str:
    return re.sub(r"^\s*20\d{2}(?:\s*[-/]\s*\d{2,4})?\s+", "", title).strip()


def _format_datetime(value) -> str:
    return value.isoformat().replace("+00:00", "")


def _google_calendar_url(event: Event) -> str | None:
    if not event.event_date:
        return None

    start = event.event_date
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = start + timedelta(hours=3)

    params = {
        "action": "TEMPLATE",
        "text": _clean_event_title(event.title),
        "dates": f"{start.strftime('%Y%m%dT%H%M%SZ')}/{end.strftime('%Y%m%dT%H%M%SZ')}",
        "details": event.url,
    }
    if event.venue_name:
        params["location"] = event.venue_name
    return f"https://calendar.google.com/calendar/render?{urlencode(params)}"
