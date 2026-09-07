from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.models import Event, SourceListing, utc_now
from app.services.source_matching import CANONICAL_FIELDS, find_matching_event, reconcile_event, update_listing
from app.scrapers.base import ScrapedEvent


@dataclass
class DetectionResult:
    new_events: list[Event] = field(default_factory=list)
    updated_events: list[Event] = field(default_factory=list)
    unchanged_events: list[Event] = field(default_factory=list)
    notifications_sent: int = 0


def generate_content_hash(event: ScrapedEvent | dict) -> str:
    payload = {
        "title": _normalize(event.get("title")),
        "artist_name": _normalize(event.get("artist_name")),
        "presale_date": _normalize_datetime(event.get("presale_date")),
        "venue_name": _normalize(event.get("venue_name")),
        "event_date": _normalize_datetime(event.get("event_date")),
        "sale_date": _normalize_datetime(event.get("sale_date")),
        "url": event.get("url"),
        "status": _normalize(event.get("status") or "active"),
        "price_summary": _normalize(event.get("price_summary")),
        "currency": _normalize(event.get("currency")),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def process_events(db: Session, events: list[ScrapedEvent], *, commit: bool = True) -> DetectionResult:
    result = DetectionResult()
    touched: dict[int, tuple[Event, str | None]] = {}
    seen: dict[tuple[str, str], str | None] = {}
    for observation in events:
        scraped = dict(observation)
        for key in ("event_date", "sale_date", "presale_date"):
            value = scraped.get(key)
            if value is not None:
                scraped[key] = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        external_id = scraped.get("source_event_id") or scraped["url"]
        identity = (scraped["source_name"], external_id)
        date_key = _normalize_datetime(scraped.get("event_date"))
        if identity in seen and seen[identity] != date_key:
            raise ValueError("Multiple performances need distinct source_event_id values.")
        seen[identity] = date_key
        source = crud.get_or_create_source(db, scraped["source_name"], _source_base_url(scraped["url"]))
        listing = db.scalar(select(SourceListing).where(
            SourceListing.source_id == source.id, SourceListing.external_id == external_id,
        ))
        if listing is None:
            event = find_matching_event(db, source.id, scraped)
            if event is None:
                # Populate matching fields immediately so another source in this batch can join it.
                initial = {field: scraped[field] for field in CANONICAL_FIELDS if scraped.get(field) is not None}
                initial.setdefault("status", "active")
                event = Event(**initial, source_id=source.id, content_hash="")
                db.add(event)
                db.flush()
                touched[event.id] = (event, None)
            listing = SourceListing(event=event, source=source, external_id=external_id,
                                    title=scraped["title"], url=scraped["url"])
            db.add(listing)
        else:
            event = listing.event
        if event.id not in touched:
            touched[event.id] = (event, generate_content_hash({field: getattr(event, field) for field in CANONICAL_FIELDS}))
        update_listing(listing, scraped)
        event.last_seen_at = utc_now()
        db.flush()

    # Reconcile only once after all source observations, avoiding intermediate change alerts.
    for event, previous_hash in touched.values():
        reconcile_event(event)
        event.content_hash = generate_content_hash({field: getattr(event, field) for field in CANONICAL_FIELDS})
        if previous_hash is None:
            result.new_events.append(event)
        elif previous_hash != event.content_hash:
            event.revision += 1
            result.updated_events.append(event)
        else:
            result.unchanged_events.append(event)
    db.flush()
    if commit:
        db.commit()
    return result


def _normalize(value: object) -> str | None:
    if value is None:
        return None
    return " ".join(str(value).strip().lower().split())


def _normalize_datetime(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return _normalize(value)


def _source_base_url(url: str) -> str:
    parts = url.split("/", 3)
    if len(parts) >= 3:
        return f"{parts[0]}//{parts[2]}"
    return url
