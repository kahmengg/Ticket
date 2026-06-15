from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from app.config import settings
from app.scrapers.base import BaseScraper, ScrapedEvent


class LiveNationSGScraper(BaseScraper):
    source_name = "Live Nation Singapore"
    base_url = "https://www.livenation.sg"
    api_url = "https://www.livenation.sg/__api/search/events"
    timeout_seconds = 15
    user_agent = "TicketSaleAssistant/0.1 (+https://example.local; conservative event monitor)"

    def __init__(self, events_url: str | None = None) -> None:
        self.events_url = events_url or settings.livenation_sg_events_url

    def fetch_events(self) -> list[ScrapedEvent]:
        api_events = self._fetch_api_events()
        if api_events:
            return api_events

        response = requests.get(
            self.events_url,
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        cards = self._find_event_cards(soup)
        events = [event for card in cards if (event := self._parse_card(card))]
        return self._dedupe_by_url(events)

    def _fetch_api_events(self) -> list[ScrapedEvent]:
        documents: list[object] = []
        page = 1
        page_size = self._page_size_from_events_url()

        while True:
            response = requests.get(
                self.api_url,
                params=[*self._api_params_from_events_url(), ("Page", str(page))],
                headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()

            page_documents = data.get("documents", [])
            if not isinstance(page_documents, list) or not page_documents:
                break

            documents.extend(page_documents)
            total = data.get("total")
            if not isinstance(total, int) or len(documents) >= total or len(page_documents) < page_size:
                break
            page += 1

        events = [event for document in documents if (event := self._parse_api_document(document))]
        return self._dedupe_by_url(events)

    def _api_params_from_events_url(self) -> list[tuple[str, str]]:
        parsed = urlparse(self.events_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        params: list[tuple[str, str]] = [
            ("culture", query.get("culture", "en-SG")),
            ("CountryIds", query.get("CountryIds", "199")),
            ("PageSize", query.get("PageSize", "50")),
        ]

        genres = query.get("Genres", "")
        for index, genre in enumerate(filter(None, genres.split(","))):
            params.append((f"Genres[{index}]", genre))

        return params

    def _page_size_from_events_url(self) -> int:
        parsed = urlparse(self.events_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        try:
            return max(1, int(query.get("PageSize", "50")))
        except ValueError:
            return 50

    def _parse_api_document(self, document: object) -> ScrapedEvent | None:
        if not isinstance(document, dict):
            return None

        title = self._clean_text(document.get("name"))
        url = self._clean_text(document.get("url"))
        if not title or not url:
            return None

        venue = document.get("venue")
        venue_name = self._clean_text(venue.get("name")) if isinstance(venue, dict) else None
        lineup = document.get("lineup")
        artist_name = self._artist_from_lineup(lineup) or title

        sale_date, presale_date = self._ticket_dates(document.get("tickets"))

        return {
            "title": title,
            "artist_name": artist_name,
            "venue_name": venue_name,
            "event_date": self._parse_date_value(document.get("eventDateUtc") or document.get("eventDate")),
            "sale_date": sale_date,
            "presale_date": presale_date,
            "url": urljoin(self.base_url, url),
            "source_name": self.source_name,
        }

    def _find_event_cards(self, soup: BeautifulSoup) -> list[Tag]:
        selectors = [
            "[data-testid*='event']",
            "article",
            ".event-card",
            ".event-listing",
            "li",
        ]
        seen: set[int] = set()
        cards: list[Tag] = []
        for selector in selectors:
            for card in soup.select(selector):
                if id(card) not in seen and card.find("a", href=True):
                    seen.add(id(card))
                    cards.append(card)
        return cards

    def _parse_card(self, card: Tag) -> ScrapedEvent | None:
        link = card.find("a", href=True)
        if not link:
            return None

        title = self._text_from_first(card, ["h1", "h2", "h3", "[data-testid*='title']", ".title"])
        if not title:
            title = link.get_text(" ", strip=True)
        if not title or len(title) < 2:
            return None

        url = urljoin(self.base_url, str(link["href"]))
        event_date = self._date_from_first(card)
        venue_name = self._text_from_first(card, ["[data-testid*='venue']", ".venue", ".location"])

        return {
            "title": title,
            "artist_name": title,
            "venue_name": venue_name,
            "event_date": event_date,
            "sale_date": None,
            "presale_date": None,
            "url": url,
            "source_name": self.source_name,
        }

    def _text_from_first(self, card: Tag, selectors: list[str]) -> str | None:
        for selector in selectors:
            element = card.select_one(selector)
            if element:
                text = element.get_text(" ", strip=True)
                if text:
                    return " ".join(text.split())
        return None

    def _date_from_first(self, card: Tag) -> datetime | None:
        time_element = card.find("time")
        if isinstance(time_element, Tag):
            for attr in ("datetime", "content"):
                value = time_element.get(attr)
                if isinstance(value, str):
                    parsed = self._parse_date(value)
                    if parsed:
                        return parsed

            parsed = self._parse_date(time_element.get_text(" ", strip=True))
            if parsed:
                return parsed
        return None

    def _parse_date(self, value: str) -> datetime | None:
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None

    def _parse_date_value(self, value: object) -> datetime | None:
        if isinstance(value, str):
            return self._parse_date(value)
        return None

    def _artist_from_lineup(self, lineup: object) -> str | None:
        if not isinstance(lineup, list):
            return None
        primary = next(
            (
                item
                for item in lineup
                if isinstance(item, dict) and (item.get("isPrimary") or item.get("type") == "headline")
            ),
            None,
        )
        if isinstance(primary, dict):
            return self._clean_text(primary.get("name"))
        if lineup and isinstance(lineup[0], dict):
            return self._clean_text(lineup[0].get("name"))
        return None

    def _ticket_dates(self, tickets: object) -> tuple[datetime | None, datetime | None]:
        if not isinstance(tickets, list):
            return None, None

        sale_dates: list[datetime] = []
        presale_dates: list[datetime] = []
        for ticket in tickets:
            if not isinstance(ticket, dict):
                continue
            valid_from = self._parse_date_value(ticket.get("validFromUtc"))
            if not valid_from:
                continue

            ticket_type = self._clean_text(ticket.get("type")) or ""
            if "presale" in ticket_type.lower():
                presale_dates.append(valid_from)
            else:
                sale_dates.append(valid_from)

        return (
            min(sale_dates) if sale_dates else None,
            min(presale_dates) if presale_dates else None,
        )

    def _clean_text(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = " ".join(value.split())
        return text or None

    def _dedupe_by_url(self, events: list[ScrapedEvent]) -> list[ScrapedEvent]:
        seen: set[str] = set()
        deduped: list[ScrapedEvent] = []
        for event in events:
            if event["url"] in seen:
                continue
            seen.add(event["url"])
            deduped.append(event)
        return deduped
