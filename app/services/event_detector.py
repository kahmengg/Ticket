from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json

from sqlalchemy.orm import Session

from app import crud
from app.models import Event, utc_now
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
        "url": _normalize(event.get("url")),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def process_events(db: Session, events: list[ScrapedEvent], *, commit: bool = True) -> DetectionResult:
    result = DetectionResult()

    for scraped in events:
        # SQLite drops offsets, so normalize before persistence as well as before hashing.
        scraped = dict(scraped)
        for key in ("event_date", "sale_date", "presale_date"):
            value = scraped.get(key)
            if value is not None:
                scraped[key] = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        source = crud.get_or_create_source(
            db,
            name=scraped["source_name"],
            base_url=_source_base_url(scraped["url"]),
        )
        content_hash = generate_content_hash(scraped)
        existing = crud.get_event_by_url(db, scraped["url"])
        if existing is None:
            existing = crud.get_event_by_identity(
                db,
                title=scraped["title"],
                venue_name=scraped.get("venue_name"),
                event_date=scraped.get("event_date"),
            )

        if existing is None:
            event = Event(
                source_id=source.id,
                title=scraped["title"],
                artist_name=scraped.get("artist_name"),
                venue_name=scraped.get("venue_name"),
                event_date=scraped.get("event_date"),
                sale_date=scraped.get("sale_date"),
                presale_date=scraped.get("presale_date"),
                url=scraped["url"],
                status="active",
                content_hash=content_hash,
            )
            db.add(event)
            result.new_events.append(event)
            continue

        existing.last_seen_at = utc_now()
        # Compare stored values so changing the hash algorithm does not announce every event.
        stored_hash = generate_content_hash({key: getattr(existing, key) for key in (
            "title", "artist_name", "venue_name", "event_date", "sale_date", "presale_date", "url",
        )})
        if stored_hash != content_hash:
            existing.revision += 1
            existing.source_id = source.id
            existing.title = scraped["title"]
            existing.artist_name = scraped.get("artist_name")
            existing.venue_name = scraped.get("venue_name")
            existing.event_date = scraped.get("event_date")
            existing.sale_date = scraped.get("sale_date")
            existing.presale_date = scraped.get("presale_date")
            existing.url = scraped["url"]
            existing.content_hash = content_hash
            result.updated_events.append(existing)
        else:
            existing.content_hash = content_hash
            result.unchanged_events.append(existing)

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
