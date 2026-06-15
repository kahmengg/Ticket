from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventBase(BaseModel):
    title: str
    artist_name: str | None = None
    venue_name: str | None = None
    event_date: datetime | None = None
    sale_date: datetime | None = None
    presale_date: datetime | None = None
    url: str
    status: str = "active"


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int | None
    content_hash: str
    first_seen_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime


class HealthRead(BaseModel):
    status: str


class RunCheckRead(BaseModel):
    new_events: int
    updated_events: int
    unchanged_events: int
    notifications_sent: int


class TelegramTestRead(BaseModel):
    configured_chat_ids: list[str]
    sent: int
