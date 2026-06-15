from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    country: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, default="official")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    events: Mapped[list["Event"]] = relationship(back_populates="source")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("title", "venue_name", "event_date", name="uq_event_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    artist_name: Mapped[str | None] = mapped_column(String(255), index=True)
    venue_name: Mapped[str | None] = mapped_column(String(255), index=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sale_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    presale_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    source: Mapped[Source | None] = relationship(back_populates="events")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="event")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("event_id", "alert_type", "chat_id", name="uq_alert_event_type_chat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False, index=True)
    chat_id: Mapped[str | None] = mapped_column(String(100), index=True)
    alert_type: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    event: Mapped[Event] = relationship(back_populates="alerts")


class TelegramSubscriber(Base):
    __tablename__ = "telegram_subscribers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    from_id: Mapped[str | None] = mapped_column(String(100), index=True)
    username: Mapped[str | None] = mapped_column(String(255), index=True)
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    chat_type: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
