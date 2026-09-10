from datetime import datetime

from sqlalchemy import func, or_, select, update
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
    # A shared detail URL is no longer a unique event identifier.
    matches = list(db.scalars(select(Event).where(Event.url == url).limit(2)))
    return matches[0] if len(matches) == 1 else None


def get_event_by_identity(
    db: Session,
    title: str,
    venue_name: str | None,
    event_date: datetime | None,
) -> Event | None:
    matches = list(db.scalars(
        select(Event).where(
            Event.title == title,
            Event.venue_name == venue_name,
            Event.event_date == event_date,
        ).limit(2)
    ))
    return matches[0] if len(matches) == 1 else None


def list_events(db: Session) -> list[Event]:
    return list(db.scalars(select(Event).order_by(Event.first_seen_at.desc(), Event.id.desc())))


def _browse_statement(kind: str, now: datetime):
    from sqlalchemy import case, and_
    title = func.coalesce(func.nullif(Event.sort_title, ""), func.lower(Event.title))
    if kind == "latest":
        # Initial imports share an older group rather than pretending insertion order is recency.
        recent = Event.discovery_kind == "discovered"
        return select(Event).order_by(case((recent, 0), else_=1),
            case((recent, Event.discovered_at), else_=None).desc().nulls_last(),
            title, Event.event_date.asc().nulls_last(), Event.id)
    if kind != "upcoming":
        raise ValueError("Unknown concert list")
    return select(Event).where(
        or_(Event.status.is_(None), Event.status.not_in(["cancelled", "postponed"])),
        or_(Event.event_date >= now, and_(Event.event_date.is_(None), Event.sale_date >= now)),
    ).order_by(Event.event_date.asc().nulls_last(), title, Event.sale_date.asc().nulls_last(), Event.id)


def browse_events(db: Session, kind: str, now: datetime, cutoff: datetime, page: int = 0):
    from sqlalchemy.orm import noload
    statement = _browse_statement(kind, now).where(Event.first_seen_at <= cutoff)
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    pages = max(1, (total + 4) // 5)
    page = max(0, min(page, pages - 1))
    # Compact messages use scalar fields only; avoid loading provider relationships.
    events = list(db.scalars(statement.options(noload(Event.listings)).offset(page * 5).limit(5)))
    return events, total, page, pages


def list_latest_events(db: Session, limit: int = 5) -> list[Event]:
    return list(db.scalars(_browse_statement("latest", utc_now()).limit(limit)))


def list_upcoming_events(db: Session, now: datetime) -> list[Event]:
    return list(db.scalars(_browse_statement("upcoming", now)))


def list_upcoming_events_limited(db: Session, now: datetime, limit: int = 5) -> list[Event]:
    return list(db.scalars(_browse_statement("upcoming", now).limit(limit)))


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
        # Receiving a message records the chat without opting it into alerts.
        subscriber = TelegramSubscriber(chat_id=chat_id, is_active=False)
        db.add(subscriber)

    subscriber.from_id = from_id
    subscriber.username = username
    subscriber.first_name = first_name
    subscriber.last_name = last_name
    subscriber.chat_type = chat_type
    subscriber.last_seen_at = utc_now()
    db.flush()
    return subscriber


def activate_telegram_subscriber(db: Session, chat_id: str) -> None:
    subscriber = db.scalar(select(TelegramSubscriber).where(TelegramSubscriber.chat_id == chat_id))
    if subscriber is None:
        subscriber = TelegramSubscriber(chat_id=chat_id)
        db.add(subscriber)
    subscriber.is_active = True
    db.flush()


def telegram_subscription_state(db: Session, chat_id: str) -> bool | None:
    # None distinguishes configured test recipients from chats that explicitly stopped.
    return db.scalar(select(TelegramSubscriber.is_active).where(TelegramSubscriber.chat_id == chat_id))


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
    # A later /start must not revive messages queued before the unsubscribe.
    db.execute(update(Alert).where(
        Alert.chat_id == chat_id, Alert.delivery_state.in_(["pending", "sending"]),
    ).values(delivery_state="cancelled", lease_token=None, next_attempt_at=None))
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
