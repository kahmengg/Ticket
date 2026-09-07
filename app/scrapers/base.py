from abc import ABC, abstractmethod
from datetime import datetime
from typing import NotRequired, TypedDict


class ScrapedSaleWindow(TypedDict):
    external_id: str
    name: str
    kind: str
    starts_at: datetime | None
    ends_at: datetime | None


class ScrapedEvent(TypedDict):
    title: str
    artist_name: str | None
    venue_name: str | None
    event_date: datetime | None
    sale_date: datetime | None
    presale_date: datetime | None
    url: str
    source_name: str
    # Required for shared detail URLs; use the source's stable performance identifier.
    source_event_id: NotRequired[str]
    status: NotRequired[str | None]
    price_summary: NotRequired[str | None]
    currency: NotRequired[str | None]
    sale_windows: NotRequired[list[ScrapedSaleWindow]]


class BaseScraper(ABC):
    source_name: str
    base_url: str

    @abstractmethod
    def fetch_events(self) -> list[ScrapedEvent]:
        raise NotImplementedError
