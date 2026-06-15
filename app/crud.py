from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Alert, Event, Source, TelegramSubscriber, WatchlistKeyword, utc_now


def get_or_create_source(db: Session, name: str, base_url: str, source_type: str = "official") -> Source:
    source = db.scalar(select(Source).where(Source.name == name))
    if source:
        return source

    source = Source(name=name, base_url=base_url, source_type=source_type)
    db.add(source)
    db.flush()
    return source


def get_event_by_url(db: Session, url: str) -> Event | None:
    return db.scalar(select(Event).where(Event.url == url))


def get_event_by_identity(
    db: Session,
    title: str,
    venue_name: str | None,
    event_date: datetime | None,
) -> Event | None:
    return db.scalar(
        select(Event).where(
            Event.title == title,
            Event.venue_name == venue_name,
            Event.event_date == event_date,
        )
    )


def list_events(db: Session) -> list[Event]:
    return list(db.scalars(select(Event).order_by(Event.first_seen_at.desc(), Event.id.desc())))


def list_latest_events(db: Session, limit: int = 5) -> list[Event]:
    return list(db.scalars(select(Event).order_by(Event.first_seen_at.desc(), Event.id.desc()).limit(limit)))


def list_upcoming_events(db: Session, now: datetime) -> list[Event]:
    return list(
        db.scalars(
            select(Event)
            .where(or_(Event.event_date >= now, Event.sale_date >= now))
            .order_by(Event.event_date.asc().nulls_last(), Event.sale_date.asc().nulls_last())
        )
    )


def list_upcoming_events_limited(db: Session, now: datetime, limit: int = 5) -> list[Event]:
    return list(
        db.scalars(
            select(Event)
            .where(or_(Event.event_date >= now, Event.sale_date >= now))
            .order_by(Event.event_date.asc().nulls_last(), Event.sale_date.asc().nulls_last())
            .limit(limit)
        )
    )


def count_events(db: Session) -> int:
    return db.scalar(select(func.count(Event.id))) or 0


def alert_exists(db: Session, event_id: int, alert_type: str, chat_id: str) -> bool:
    return (
        db.scalar(
            select(Alert.id).where(
                Alert.event_id == event_id,
                Alert.alert_type == alert_type,
                Alert.chat_id == chat_id,
            )
        )
        is not None
    )


def create_alert(db: Session, event_id: int, alert_type: str, chat_id: str, message: str) -> Alert:
    alert = Alert(
        event_id=event_id,
        alert_type=alert_type,
        chat_id=chat_id,
        message=message,
        sent_at=utc_now(),
    )
    db.add(alert)
    db.flush()
    return alert


def upsert_telegram_subscriber(
    db: Session,
    chat_id: str,
    from_id: str | None = None,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    chat_type: str | None = None,
) -> TelegramSubscriber:
    subscriber = db.scalar(select(TelegramSubscriber).where(TelegramSubscriber.chat_id == chat_id))
    if subscriber is None:
        subscriber = TelegramSubscriber(chat_id=chat_id)
        db.add(subscriber)

    subscriber.from_id = from_id
    subscriber.username = username
    subscriber.first_name = first_name
    subscriber.last_name = last_name
    subscriber.chat_type = chat_type
    subscriber.is_active = True
    subscriber.last_seen_at = utc_now()
    db.flush()
    return subscriber


def list_active_telegram_chat_ids(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(TelegramSubscriber.chat_id)
            .where(TelegramSubscriber.is_active.is_(True))
            .order_by(TelegramSubscriber.created_at.asc())
        )
    )


def deactivate_telegram_subscriber(db: Session, chat_id: str) -> bool:
    subscriber = db.scalar(select(TelegramSubscriber).where(TelegramSubscriber.chat_id == chat_id))
    if subscriber is None:
        return False

    subscriber.is_active = False
    subscriber.last_seen_at = utc_now()
    db.flush()
    return True


def upsert_watchlist_keyword(
    db: Session,
    chat_id: str,
    keyword: str,
    normalized_keyword: str,
    compact_keyword: str,
) -> WatchlistKeyword:
    watch = db.scalar(
        select(WatchlistKeyword).where(
            WatchlistKeyword.chat_id == chat_id,
            WatchlistKeyword.normalized_keyword == normalized_keyword,
        )
    )
    if watch is None:
        watch = WatchlistKeyword(
            chat_id=chat_id,
            keyword=keyword,
            normalized_keyword=normalized_keyword,
            compact_keyword=compact_keyword,
        )
        db.add(watch)
    else:
        watch.keyword = keyword
        watch.compact_keyword = compact_keyword
        watch.is_active = True
    db.flush()
    return watch


def list_active_watchlist_keywords(db: Session, chat_id: str | None = None) -> list[WatchlistKeyword]:
    statement = select(WatchlistKeyword).where(WatchlistKeyword.is_active.is_(True))
    if chat_id is not None:
        statement = statement.where(WatchlistKeyword.chat_id == chat_id)
    return list(db.scalars(statement.order_by(WatchlistKeyword.keyword.asc())))


def deactivate_watchlist_keyword(db: Session, chat_id: str, normalized_keyword: str) -> bool:
    watch = db.scalar(
        select(WatchlistKeyword).where(
            WatchlistKeyword.chat_id == chat_id,
            WatchlistKeyword.normalized_keyword == normalized_keyword,
            WatchlistKeyword.is_active.is_(True),
        )
    )
    if watch is None:
        return False
    watch.is_active = False
    db.flush()
    return True
