from abc import ABC, abstractmethod
from datetime import datetime
from typing import TypedDict


class ScrapedEvent(TypedDict):
    title: str
    artist_name: str | None
    venue_name: str | None
    event_date: datetime | None
    sale_date: datetime | None
    presale_date: datetime | None
    url: str
    source_name: str


class BaseScraper(ABC):
    source_name: str
    base_url: str

    @abstractmethod
    def fetch_events(self) -> list[ScrapedEvent]:
        raise NotImplementedError
