"""Conservative performance matching and deterministic field selection."""
from datetime import datetime, timezone
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, SaleWindow, SourceListing, utc_now

CANONICAL_FIELDS = (
    "title", "artist_name", "venue_name", "event_date", "sale_date", "presale_date",
    "url", "status", "price_summary", "currency",
)


def normalized(value: str | None) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value or "").casefold()))


def normalized_venue(value: str | None) -> str:
    # Country suffixes differ across providers; preserve names beginning with Singapore.
    return re.sub(r" singapore$", "", normalized(value))


def _compatible_title(left: str, right: str) -> bool:
    if normalized(left) == normalized(right):
        return True
    # Only tolerate punctuation, a leading year, and a Singapore suffix; no fuzzy matching.
    def simplified(value):
        value = re.sub(r"^20\d{2}\s+", "", normalized(value))
        return re.sub(r"(?: in)? singapore$", "", value).strip()
    return bool(simplified(left)) and simplified(left) == simplified(right)


def find_matching_event(db: Session, source_id: int, scraped: dict) -> Event | None:
    if scraped.get("event_date") is None or not normalized(scraped.get("venue_name")):
        return None
    candidates = db.scalars(select(Event).where(Event.event_date == scraped["event_date"])).all()
    matches = []
    for event in candidates:
        # Distinct performance IDs from one provider are not automatically merged.
        if any(listing.source_id == source_id for listing in event.listings):
            continue
        if normalized_venue(event.venue_name) != normalized_venue(scraped.get("venue_name")):
            continue
        if not _compatible_title(event.title, scraped["title"]):
            continue
        left_artist, right_artist = normalized(event.artist_name), normalized(scraped.get("artist_name"))
        if left_artist and right_artist and left_artist != right_artist:
            # Some scrapers use the full event title as an artist fallback.
            if not (_compatible_title(event.artist_name, event.title) or
                    _compatible_title(scraped["artist_name"], scraped["title"])):
                continue
        matches.append(event)
    return matches[0] if len(matches) == 1 else None


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _json_value(value):
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def update_listing(listing: SourceListing, scraped: dict) -> None:
    listing.observed_data = _json_value(scraped)
    listing.last_seen_at = utc_now()
    for field in CANONICAL_FIELDS:
        value = scraped.get(field)
        # Missing extraction data must not erase the last known value.
        if value is not None and value != "":
            setattr(listing, field, value)
    windows = scraped.get("sale_windows")
    if windows:
        # Named windows replace our generic fallback for that kind, not other named presales.
        kinds = {window["kind"] for window in windows if window.get("starts_at") is not None}
        ids = {window["external_id"] for window in windows}
        listing.sale_windows[:] = [window for window in listing.sale_windows
                                   if not (window.external_id in {"general", "presale"}
                                           and window.kind in kinds and window.external_id not in ids)]
    if windows is None:
        windows = [dict(external_id=kind, name=name, kind=kind, starts_at=scraped[field], ends_at=None)
                   for field, kind, name in (("sale_date", "general", "General sale"), ("presale_date", "presale", "Presale"))
                   if scraped.get(field) is not None]
    for incoming in windows:
        if incoming["kind"] not in {"general", "presale"}:
            raise ValueError("Sale-window kind must be general or presale.")
        window = next((item for item in listing.sale_windows if item.external_id == incoming["external_id"]), None)
        if window is None:
            window = SaleWindow(external_id=incoming["external_id"], name=incoming["name"], kind=incoming["kind"])
            listing.sale_windows.append(window)
        for field in ("name", "kind", "starts_at", "ends_at"):
            value = incoming.get(field)
            if value is not None:
                setattr(window, field, _utc(value) if field.endswith("_at") else value)
    # Named windows may be the only sale information a source provides.
    for field, kind in (("sale_date", "general"), ("presale_date", "presale")):
        dates = [_utc(item.starts_at) for item in listing.sale_windows if item.kind == kind and item.starts_at]
        if scraped.get(field) is None and windows and dates:
            setattr(listing, field, min(dates))


def _priority(listing: SourceListing, field: str):
    preferred = ("Ticketmaster Singapore", "Ticketmaster Discovery Singapore", "Live Nation Singapore") if field in {
        "sale_date", "presale_date", "status", "price_summary", "currency",
    } else ("Live Nation Singapore", "Ticketmaster Singapore", "Ticketmaster Discovery Singapore")
    name = listing.source.name
    rank = preferred.index(name) if name in preferred else len(preferred)
    return rank, name, listing.external_id


def reconcile_event(event: Event) -> None:
    provenance = dict(event.field_provenance or {})
    for field in CANONICAL_FIELDS:
        if field == "currency":
            continue
        available = [listing for listing in event.listings if getattr(listing, field) not in (None, "")]
        if not available:
            continue
        selected = min(available, key=lambda listing: _priority(listing, field))
        setattr(event, field, getattr(selected, field))
        provenance[field] = selected.id
        if field == "price_summary":
            # Never combine one provider's price with a different provider's currency.
            event.currency = selected.currency
            if selected.currency:
                provenance["currency"] = selected.id
            else:
                provenance.pop("currency", None)
        if field == "url":
            event.source_id = selected.source_id
    event.field_provenance = provenance
