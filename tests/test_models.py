from datetime import datetime, timezone

from app.models import Alert, Artist, Event, Source, Venue
from app.services.event_detector import generate_content_hash


def test_database_model_creation(db_session):
    artist = Artist(name="Example Artist")
    venue = Venue(name="National Stadium", country="Singapore")
    source = Source(name="Example Source", base_url="https://example.com", source_type="official")
    db_session.add_all([artist, venue, source])
    db_session.flush()

    event_data = {
        "title": "Example Artist",
        "artist_name": artist.name,
        "venue_name": venue.name,
        "event_date": datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        "sale_date": None,
        "presale_date": None,
        "url": "https://example.com/events/example-artist",
        "source_name": source.name,
    }
    event = Event(
        source_id=source.id,
        title=event_data["title"],
        artist_name=event_data["artist_name"],
        venue_name=event_data["venue_name"],
        event_date=event_data["event_date"],
        sale_date=event_data["sale_date"],
        presale_date=event_data["presale_date"],
        url=event_data["url"],
        content_hash=generate_content_hash(event_data),
    )
    db_session.add(event)
    db_session.flush()

    alert = Alert(event_id=event.id, chat_id="123", alert_type="telegram", message="New event", sent_at=None)
    db_session.add(alert)
    db_session.commit()

    assert artist.id is not None
    assert venue.id is not None
    assert source.id is not None
    assert event.id is not None
    assert alert.id is not None
