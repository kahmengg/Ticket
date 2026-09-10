from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
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
    baseline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str] = mapped_column(String(20), default="never", server_default="never")
    last_error: Mapped[str | None] = mapped_column(Text)
    last_event_count: Mapped[int] = mapped_column(default=0, server_default="0")
    last_warnings: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    events: Mapped[list["Event"]] = relationship(back_populates="source")


class Event(Base):
    __tablename__ = "events"
    # Keep metadata consistent with the additive migration and paged browsing queries.
    __table_args__ = (
        Index("ix_events_browse_discovery", "discovery_kind", "discovered_at", "sort_title", "event_date", "id"),
        Index("ix_events_browse_upcoming", "event_date", "sort_title", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    artist_name: Mapped[str | None] = mapped_column(String(255), index=True)
    venue_name: Mapped[str | None] = mapped_column(String(255), index=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sale_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    presale_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A detail page may advertise several performances; listing IDs carry identity.
    url: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    price_summary: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(String(3))
    field_provenance: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(50), default="active", index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(default=1, server_default="1")
    discovery_kind: Mapped[str] = mapped_column(String(20), default="legacy", server_default="legacy", index=True)
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sort_title: Mapped[str] = mapped_column(String(500), default="", server_default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    source: Mapped[Source | None] = relationship(back_populates="events")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="event")
    listings: Mapped[list["SourceListing"]] = relationship(back_populates="event", lazy="selectin")


class SourceListing(Base):
    __tablename__ = "source_listings"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_source_listing_identity"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(1000))
    url: Mapped[str] = mapped_column(String(1000), index=True)
    title: Mapped[str] = mapped_column(String(500))
    artist_name: Mapped[str | None] = mapped_column(String(255))
    venue_name: Mapped[str | None] = mapped_column(String(255))
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sale_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    presale_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(50))
    price_summary: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(String(3))
    # Keep the latest observation separately from retained, last-known field values.
    observed_data: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    event: Mapped[Event] = relationship(back_populates="listings")
    source: Mapped[Source] = relationship(lazy="joined")
    sale_windows: Mapped[list["SaleWindow"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan", lazy="selectin",
    )

    @property
    def source_name(self) -> str:
        return self.source.name


class SaleWindow(Base):
    __tablename__ = "sale_windows"
    __table_args__ = (UniqueConstraint("listing_id", "external_id", name="uq_listing_sale_window"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("source_listings.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    listing: Mapped[SourceListing] = relationship(back_populates="sale_windows")


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
    delivery_state: Mapped[str] = mapped_column(String(20), default="sent", server_default="sent", index=True)
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    sale_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class WatchlistKeyword(Base):
    __tablename__ = "watchlist_keywords"
    __table_args__ = (
        UniqueConstraint("chat_id", "normalized_keyword", name="uq_watchlist_chat_keyword"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chat_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    compact_keyword: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
