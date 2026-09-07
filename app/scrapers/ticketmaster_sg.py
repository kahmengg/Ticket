"""Read public concert announcements, never ticket queues or checkout pages."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
import time
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedEvent

SGT = timezone(timedelta(hours=8))
MONTHS = {name: index for index, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


class SourceFetchError(RuntimeError):
    pass


def parse_local_datetime(value: str, default_date: datetime | None = None) -> datetime | None:
    """Require a time and a known date; do not invent midnight or the current year."""
    date = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s*,?\s*(20\d{2})", value, re.I)
    clock = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b", value, re.I)
    if clock is None:
        return None
    if date:
        day, month, year = int(date[1]), MONTHS.get(date[2][:3].lower()), int(date[3])
        if month is None:
            return None
    elif default_date:
        local = default_date.astimezone(SGT)
        day, month, year = local.day, local.month, local.year
    else:
        return None
    hour, minute = int(clock[1]), int(clock[2] or 0)
    if not 1 <= hour <= 12:
        return None
    hour = hour % 12 + (12 if clock[3].lower().startswith("p") else 0)
    try:
        return datetime(year, month, day, hour, minute, tzinfo=SGT).astimezone(timezone.utc)
    except ValueError:
        return None


class TicketmasterSGScraper(BaseScraper):
    source_name = "Ticketmaster Singapore"
    base_url = "https://ticketmaster.sg"
    events_url = "https://ticketmaster.sg/categories/concerts"
    max_pages = 20
    max_details = 200
    max_seconds = 480

    def __init__(self):
        self.warnings: list[str] = []
        self.errors: list[str] = []

    @staticmethod
    def detail_url(value: str) -> str:
        parsed = urlsplit(urljoin(TicketmasterSGScraper.base_url, value))
        if parsed.scheme != "https" or parsed.netloc != "ticketmaster.sg" or not re.fullmatch(r"/activity/detail/[\w-]+", parsed.path):
            raise SourceFetchError("Unexpected Ticketmaster detail URL.")
        return f"https://ticketmaster.sg{parsed.path}"

    def listing_urls(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        return list(dict.fromkeys(self.detail_url(link["href"]) for link in soup.select(
            '.listing-container a[href*="/activity/detail/"]')))

    def fetch_events(self) -> list[ScrapedEvent]:
        from playwright.sync_api import Error as BrowserError, sync_playwright

        self.warnings = []
        self.errors = []
        deadline = time.monotonic() + self.max_seconds
        with sync_playwright() as playwright:
            # A fresh browser context reads public pages without user cookies or authentication.
            browser = playwright.chromium.launch(channel="chromium", headless=True)
            try:
                context = browser.new_context(locale="en-SG", timezone_id="Asia/Singapore",
                                              user_agent="TicketSaleAssistant/0.2 (concert announcement monitor)")
                page = context.new_page()
                page.set_default_timeout(20000)
                self._navigate(page, self.events_url, '.listing-container a[href*="/activity/detail/"]')
                for _ in range(self.max_pages):
                    marker = page.locator(".page-show-more")
                    if marker.count() == 0:
                        break
                    before = marker.get_attribute("data-parameter")
                    time.sleep(1)
                    page.locator(".page-show-more a").click()
                    page.wait_for_function("previous => { const m = document.querySelector('.page-show-more'); return !m || m.getAttribute('data-parameter') !== previous; }", arg=before)
                    if time.monotonic() > deadline:
                        raise SourceFetchError("Ticketmaster listing exceeded the time limit.")
                else:
                    raise SourceFetchError("Ticketmaster pagination exceeded the page limit.")
                urls = self.listing_urls(page.content())
                if not urls or len(urls) > self.max_details:
                    raise SourceFetchError("Ticketmaster listing was empty or exceeded the detail limit.")
                events = []
                for url in urls:
                    if time.monotonic() > deadline:
                        self.errors.append("Ticketmaster detail fetch exceeded the time limit.")
                        break
                    time.sleep(1)
                    try:
                        self._navigate(page, url, "#eventListing tbody tr")
                        events.extend(self.parse_detail(page.content(), url))
                    except (SourceFetchError, BrowserError) as exc:
                        self.errors.append(f"{url}: {type(exc).__name__}")
                if not events:
                    raise SourceFetchError("No Ticketmaster performances could be read.")
                return events
            finally:
                browser.close()

    @staticmethod
    def _navigate(page, url: str, selector: str):
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if response is None or response.status >= 400:
            raise SourceFetchError(f"Ticketmaster returned HTTP {response.status if response else 'unknown'}.")
        if urlsplit(page.url).netloc != "ticketmaster.sg":
            raise SourceFetchError("Ticketmaster redirected away from its public site.")
        page.locator(selector).first.wait_for(state="attached")

    def parse_detail(self, html: str, url: str) -> list[ScrapedEvent]:
        url = self.detail_url(url)
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("#eventListing tbody tr")
        if not rows:
            raise SourceFetchError("Ticketmaster performance table was not found.")
        windows = self._sale_windows(soup)
        price_summary = self._prices(soup)
        artist = None
        for text in soup.select_one("#synopsis").stripped_strings if soup.select_one("#synopsis") else []:
            match = re.search(r"To Connect with\s+(.+)", text, re.I)
            if match:
                artist = match[1].strip()[:255]
                break
        events = []
        seen = set()
        for row in rows:
            cells = row.find_all("td", recursive=False)
            if len(cells) < 3:
                raise SourceFetchError("Ticketmaster performance row has missing columns.")
            texts = [cell.get_text(" ", strip=True) for cell in cells]
            performance_id = row.get("data-key") or row.get("id")
            event_date = parse_local_datetime(texts[0])
            if not performance_id or not event_date or not texts[1] or not texts[2]:
                raise SourceFetchError("Ticketmaster performance identity/date is incomplete.")
            identity = f"{urlsplit(url).path.rsplit('/', 1)[-1]}:{performance_id}"
            if identity in seen:
                raise SourceFetchError("Ticketmaster returned duplicate performance IDs.")
            seen.add(identity)
            status_text = f"{texts[1]} {texts[3] if len(texts) > 3 else ''}".lower()
            status = next((value for needle, value in (
                ("cancelled", "cancelled"), ("canceled", "cancelled"), ("postponed", "postponed"),
                ("sold out", "sold_out"), ("unavailable", "unavailable"), ("find tickets", "tickets_listed"),
            ) if needle in status_text), None)
            dates = lambda kind: [window["starts_at"] for window in windows if window["kind"] == kind and window["starts_at"]]
            events.append(dict(title=texts[1], artist_name=artist, venue_name=texts[2], event_date=event_date,
                               sale_date=min(dates("general"), default=None), presale_date=min(dates("presale"), default=None),
                               url=url, source_name=self.source_name, source_event_id=identity, status=status,
                               price_summary=price_summary, currency="SGD" if price_summary else None, sale_windows=windows))
        return events

    def _sale_windows(self, soup) -> list[dict]:
        windows = {}
        for node in soup.select("#prices li, #prices p"):
            value = " ".join(node.get_text(" ", strip=True).split())
            match = re.match(r"([^:]{0,120}(?:presale|pre-sale|priority sale|general sale|general on-sale|general onsale))\s*:\s*(.+)", value, re.I)
            if not match:
                continue
            name, schedule = match[1], match[2]
            # Eligibility prose can repeat the same label; only parse dated schedules.
            if not re.match(r"(?:[A-Za-z]+\s*,?\s+)?\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+", schedule):
                continue
            if not re.search(r"\b20\d{2}\b", schedule):
                self.warnings.append(f"Sale year not published: {name}")
                continue
            parts = re.split(r"\s+to\s+", schedule, maxsplit=1, flags=re.I)
            start = parse_local_datetime(parts[0])
            if start is None:
                self.warnings.append(f"Unparsed sale schedule: {name}")
                continue
            end = parse_local_datetime(parts[1], start) if len(parts) > 1 else None
            if end and end < start:
                end = None
                self.warnings.append(f"Ambiguous sale end: {name}")
            key = re.sub(r"\W+", "-", name.casefold()).strip("-")
            windows[key] = dict(external_id=key, name=name, kind="general" if "general" in name.lower() else "presale", starts_at=start, ends_at=end)
        return list(windows.values())

    @staticmethod
    def _prices(soup) -> str | None:
        section = soup.select_one("#prices")
        if section is None:
            return None
        text = section.get_text(" ", strip=True)
        # Stop before booking-fee/VIP explanations so fees and unrelated numbers aren't ticket prices.
        text = re.split(r"Prices may vary|Applicable booking fees|booking fee|Will there be|Are there VIP|When do tickets", text, maxsplit=1, flags=re.I)[0]
        values = [Decimal(value.replace(",", "")) for value in re.findall(r"(?:S\$|SGD\s*|\$)\s*(\d[\d,]*(?:\.\d{2})?)", text)]
        if not values:
            return None
        low, high = min(values), max(values)
        return f"SGD {low}" + (f"–{high}" if high != low else "") + " (published prices; booking fees may apply)"
