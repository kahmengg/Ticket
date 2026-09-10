from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import crud
from app.models import Event
from app.services.notifications import _clean_event_title, _format_datetime
from app.services.watchlist import add_watch_keyword, matching_events_for_keyword, remove_watch_keyword


HELP_MESSAGE = """Ticket Sale Assistant commands:
/start - subscribe to alerts
/upcoming - browse upcoming concerts (Next/Previous)
/latest - browse newest discoveries (Next/Previous)
/watch artist - watch an artist or event keyword
/watchlist - show your watched keywords
/unwatch artist - remove a watched keyword
/stop - unsubscribe from alerts
/help - show this help"""


def handle_telegram_command(text: str, chat_id: str, db: Session) -> str | None:
    command = _command_name(text)
    if command == "/help":
        return HELP_MESSAGE
    if command == "/start":
        crud.activate_telegram_subscriber(db, chat_id)
        db.commit()
        return "You're subscribed to Ticket Sale Assistant alerts. I'll message this chat when new concerts are detected."
    if command == "/stop":
        crud.deactivate_telegram_subscriber(db, chat_id)
        db.commit()
        return "You've been unsubscribed from Ticket Sale Assistant alerts. Send /start to subscribe again."
    if command == "/upcoming":
        events = crud.list_upcoming_events_limited(db, datetime.now(timezone.utc), limit=5)
        return _format_event_list("Upcoming concerts", events)
    if command == "/latest":
        events = crud.list_latest_events(db, limit=5)
        return _format_event_list("Latest concerts found", events)
    if command == "/watch":
        keyword = _command_argument(text)
        if not keyword:
            return "Usage: /watch artist name\nExample: /watch babymonster"
        try:
            watch = add_watch_keyword(db, chat_id, keyword)
        except ValueError as exc:
            return str(exc)
        db.commit()
        matches = matching_events_for_keyword(db, watch.keyword, limit=3)
        subscription_note = ""
        if crud.telegram_subscription_state(db, chat_id) is not True:
            subscription_note = "\nAlerts are paused. Send /start to receive notifications."
        if not matches:
            return f"Watching: {watch.keyword}\nNo matching concerts found yet.{subscription_note}"
        return f"Watching: {watch.keyword}{subscription_note}\n\n{_format_event_list('Matching concerts already found', matches)}"
    if command == "/watchlist":
        watches = crud.list_active_watchlist_keywords(db, chat_id=chat_id)
        if not watches:
            return "Your watchlist is empty. Add one with /watch artist name"
        lines = ["Your watchlist:"]
        lines.extend(f"- {watch.keyword}" for watch in watches)
        return "\n".join(lines)
    if command == "/unwatch":
        keyword = _command_argument(text)
        if not keyword:
            return "Usage: /unwatch artist name\nExample: /unwatch babymonster"
        removed = remove_watch_keyword(db, chat_id, keyword)
        db.commit()
        if removed:
            return f"Removed from watchlist: {keyword}"
        return f"That keyword was not in your active watchlist: {keyword}"
    return None


def _command_name(text: str) -> str:
    first_word = text.strip().split(maxsplit=1)[0].lower() if text.strip() else ""
    return first_word.split("@", maxsplit=1)[0]


def _command_argument(text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _format_event_list(title: str, events: list[Event]) -> str:
    if not events:
        return f"{title}\nNo concerts found yet."

    sections = [title]
    for index, event in enumerate(events, start=1):
        sections.append(f"{index}. {_compact_event_message(event)}")
    return "\n\n".join(sections)


def _compact_event_message(event: Event) -> str:
    # Compact command replies need no calendar links or provider relationship queries.
    lines = [_clean_event_title(event.title)]
    for label, value in (("Venue", event.venue_name),
                         ("Event date", _format_datetime(event.event_date) if event.event_date else None),
                         ("Sale date", _format_datetime(event.sale_date) if event.sale_date else None),
                         ("Presale date", _format_datetime(event.presale_date) if event.presale_date else None),
                         ("Prices", event.price_summary), ("Status", event.status)):
        if value:
            lines.append(f"{label}: {value}")
    lines.append(f"URL: {event.url}")
    return "\n".join(lines)
