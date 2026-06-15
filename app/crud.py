from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Alert, Event, Source, TelegramSubscriber, utc_now


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


def list_upcoming_events(db: Session, now: datetime) -> list[Event]:
    return list(
        db.scalars(
            select(Event)
            .where(or_(Event.event_date >= now, Event.sale_date >= now))
            .order_by(Event.event_date.asc().nulls_last(), Event.sale_date.asc().nulls_last())
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
