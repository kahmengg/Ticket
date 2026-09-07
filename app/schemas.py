from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SaleWindowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    kind: str
    starts_at: datetime | None
    ends_at: datetime | None


class SourceListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_id: int
    source_name: str
    external_id: str
    url: str
    title: str
    artist_name: str | None
    venue_name: str | None
    event_date: datetime | None
    sale_date: datetime | None
    presale_date: datetime | None
    status: str | None
    price_summary: str | None
    currency: str | None
    last_seen_at: datetime
    sale_windows: list[SaleWindowRead] = Field(default_factory=list)


class EventBase(BaseModel):
    title: str
    artist_name: str | None = None
    venue_name: str | None = None
    event_date: datetime | None = None
    sale_date: datetime | None = None
    presale_date: datetime | None = None
    url: str
    status: str = "active"
    price_summary: str | None = None
    currency: str | None = None


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int | None
    content_hash: str
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime
    field_provenance: dict[str, int] = Field(default_factory=dict)
    listings: list[SourceListingRead] = Field(default_factory=list)


class HealthRead(BaseModel):
    status: str


class SourceCheckRead(BaseModel):
    name: str
    status: str
    events: int
    seeded: bool
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SourceStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    baseline_at: datetime | None
    last_check_at: datetime | None
    last_success_at: datetime | None
    last_status: str
    last_error: str | None
    last_event_count: int
    last_warnings: list[str]


class RunCheckRead(BaseModel):
    new_events: int
    updated_events: int
    unchanged_events: int
    notifications_sent: int
    sources: list[SourceCheckRead] = Field(default_factory=list)


class RunRemindersRead(BaseModel):
    notifications_sent: int


class TelegramTestRead(BaseModel):
    configured_chat_count: int
    sent: int
