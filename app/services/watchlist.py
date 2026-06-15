import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app import crud
from app.models import Event, WatchlistKeyword


MIN_KEYWORD_LENGTH = 2
BLOCKED_KEYWORDS = {"the", "concert", "concerts", "event", "events", "singapore", "sg", "tour"}


@dataclass(frozen=True)
class NormalizedKeyword:
    keyword: str
    normalized: str
    compact: str


@dataclass(frozen=True)
class WatchMatch:
    chat_id: str
    keyword: str
    event: Event


def normalize_keyword(raw_keyword: str) -> NormalizedKeyword:
    keyword = " ".join(raw_keyword.strip().split())
    normalized = normalize_text(keyword)
    compact = compact_text(keyword)
    return NormalizedKeyword(keyword=keyword, normalized=normalized, compact=compact)


def validate_watch_keyword(raw_keyword: str) -> NormalizedKeyword:
    normalized = normalize_keyword(raw_keyword)
    if len(normalized.compact) < MIN_KEYWORD_LENGTH:
        raise ValueError("Watch keyword is too short.")
    if normalized.normalized in BLOCKED_KEYWORDS:
        raise ValueError("Watch keyword is too broad. Try an artist or event name.")
    return normalized


def add_watch_keyword(db: Session, chat_id: str, raw_keyword: str) -> WatchlistKeyword:
    keyword = validate_watch_keyword(raw_keyword)
    return crud.upsert_watchlist_keyword(
        db,
        chat_id=chat_id,
        keyword=keyword.keyword,
        normalized_keyword=keyword.normalized,
        compact_keyword=keyword.compact,
    )


def remove_watch_keyword(db: Session, chat_id: str, raw_keyword: str) -> bool:
    keyword = normalize_keyword(raw_keyword)
    return crud.deactivate_watchlist_keyword(db, chat_id, keyword.normalized)


def matching_events_for_keyword(db: Session, raw_keyword: str, limit: int = 5) -> list[Event]:
    keyword = normalize_keyword(raw_keyword)
    matches = [event for event in crud.list_events(db) if event_matches_keyword(event, keyword)]
    return matches[:limit]


def event_matches_keyword(event: Event, keyword: NormalizedKeyword | WatchlistKeyword) -> bool:
    normalized_keyword = keyword.normalized if isinstance(keyword, NormalizedKeyword) else keyword.normalized_keyword
    compact_keyword = keyword.compact if isinstance(keyword, NormalizedKeyword) else keyword.compact_keyword
    event_text = event_search_text(event)
    return normalized_keyword in normalize_text(event_text) or compact_keyword in compact_text(event_text)


def matched_watchlists_for_event(db: Session, event: Event) -> list[WatchMatch]:
    matches: list[WatchMatch] = []
    for watch in crud.list_active_watchlist_keywords(db):
        if event_matches_keyword(event, watch):
            matches.append(WatchMatch(chat_id=watch.chat_id, keyword=watch.keyword, event=event))
    return matches


def sale_reminder_matches(db: Session, reminder_hours: int, now: datetime | None = None) -> list[WatchMatch]:
    now = now or datetime.now(timezone.utc)
    window_end = now + timedelta(hours=reminder_hours)
    matches: list[WatchMatch] = []
    for event in crud.list_events(db):
        sale_date = event.sale_date
        if sale_date is None:
            continue
        if sale_date.tzinfo is None:
            sale_date = sale_date.replace(tzinfo=timezone.utc)
        if now <= sale_date <= window_end:
            matches.extend(matched_watchlists_for_event(db, event))
    return matches


def event_search_text(event: Event) -> str:
    return " ".join(
        value
        for value in [
            event.title,
            event.artist_name,
            event.venue_name,
        ]
        if value
    )


def normalize_text(value: str) -> str:
    lowered = value.lower()
    words = re.findall(r"[\w]+", lowered, flags=re.UNICODE)
    return " ".join(words)


def compact_text(value: str) -> str:
    return "".join(re.findall(r"[\w]+", value.lower(), flags=re.UNICODE))
