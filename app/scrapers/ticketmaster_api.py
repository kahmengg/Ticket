"""Official Discovery API adapter; coverage is verified separately from website coverage."""
from datetime import datetime, timezone
import time
from urllib.parse import urlsplit

import requests

from app.scrapers.base import BaseScraper
from app.scrapers.ticketmaster_sg import SourceFetchError


def timestamp(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # An unspecified timezone is not a reliable sale or performance instant.
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


class TicketmasterAPIScraper(BaseScraper):
    # Separate identity namespace prevents API IDs colliding with website performance IDs.
    source_name = "Ticketmaster Discovery Singapore"
    base_url = "https://app.ticketmaster.com"
    api_url = base_url + "/discovery/v2/events.json"

    def __init__(self, api_key):
        self.api_key = api_key
        self.errors = []
        self.warnings = []

    def fetch_events(self):
        if not self.api_key:
            raise SourceFetchError("Configure TICKETMASTER_API_KEY to use the Discovery API.")
        self.errors, self.warnings = [], []
        events, seen = [], set()
        for page in range(5):
            if page:
                time.sleep(1)
            try:
                response = requests.get(self.api_url, params=dict(apikey=self.api_key,
                    countryCode="SG", classificationName="music", size=200, page=page),
                    timeout=30, allow_redirects=False)
            except requests.RequestException:
                # requests exceptions can contain the API key in the URL.
                raise SourceFetchError("Ticketmaster Discovery API connection failed.") from None
            if response.status_code != 200:
                raise SourceFetchError(f"Ticketmaster Discovery API returned HTTP {response.status_code}.")
            try:
                data = response.json()
                rows = data.get("_embedded", {}).get("events", [])
                total_pages = data["page"]["totalPages"]
                if not isinstance(rows, list) or not isinstance(total_pages, int) or total_pages < 0:
                    raise ValueError()
                for row in rows:
                    event = self.parse_event(row)
                    if event["source_event_id"] not in seen:
                        events.append(event)
                        seen.add(event["source_event_id"])
            except (KeyError, ValueError, TypeError, AttributeError):
                raise SourceFetchError("Ticketmaster Discovery API returned an invalid event response.") from None
            if page + 1 >= total_pages:
                break
        else:
            raise SourceFetchError("Ticketmaster Discovery API exceeded the pagination limit.")
        if not events:
            raise SourceFetchError("Ticketmaster Discovery API returned no Singapore music events; catalogue coverage is unverified.")
        return events

    def parse_event(self, row):
        event_id, title, url = row["id"], row["name"], row["url"]
        if not event_id or not title or urlsplit(url).scheme != "https":
            raise ValueError()
        embedded = row.get("_embedded", {})
        venues = embedded.get("venues", [])
        venue = next((v for v in venues if v.get("country", {}).get("countryCode") == "SG"), None)
        if venue is None:
            raise ValueError()
        dates, sales = row.get("dates", {}), row.get("sales", {})
        start = dates.get("start", {})
        event_date = None if any(start.get(flag) for flag in ("dateTBD", "dateTBA", "timeTBA", "noSpecificTime")) else timestamp(start.get("dateTime"))
        windows = []
        public = sales.get("public", {})
        for kind, name, sale in [("general", "General sale", public)] + [
                ("presale", p.get("name") or "Presale", p) for p in sales.get("presales", [])]:
            date = None if sale.get("startTBD") else timestamp(sale.get("startDateTime"))
            if date:
                windows.append(dict(external_id=f"{kind}:{name}", kind=kind, name=name,
                                    starts_at=date, ends_at=timestamp(sale.get("endDateTime"))))
        prices = [p for p in row.get("priceRanges", []) if p.get("currency") == "SGD"
                  and isinstance(p.get("min"), (float, int)) and isinstance(p.get("max"), (float, int))]
        price = f"SGD {min(p['min'] for p in prices):g}–{max(p['max'] for p in prices):g}" if prices else None
        attractions = embedded.get("attractions", [])
        return dict(source_name=self.source_name, source_event_id=str(event_id), title=title, url=url,
                    artist_name=attractions[0].get("name") if len(attractions) == 1 else None,
                    venue_name=venue.get("name"), event_date=event_date,
                    sale_date=min((w["starts_at"] for w in windows if w["kind"] == "general"), default=None),
                    presale_date=min((w["starts_at"] for w in windows if w["kind"] == "presale"), default=None),
                    sale_windows=windows, price_summary=price, currency="SGD" if price else None,
                    status={"canceled": "cancelled", "postponed": "postponed", "onsale": "tickets_listed",
                            "offsale": "unavailable", "rescheduled": "rescheduled"}.get(dates.get("status", {}).get("code")))
