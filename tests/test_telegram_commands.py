from datetime import datetime, timezone

from app import crud
from app.models import Event
from app.services.event_detector import generate_content_hash
from app.services.telegram_commands import handle_telegram_command


def sample_event(title: str, url: str, event_date: datetime):
    event_data = {
        "title": title,
        "artist_name": title,
        "venue_name": "Singapore Indoor Stadium",
        "event_date": event_date,
        "sale_date": datetime(2026, 6, 11, 4, 0, tzinfo=timezone.utc),
        "presale_date": None,
        "url": url,
        "source_name": "Live Nation Singapore",
    }
    return Event(
        title=event_data["title"],
        artist_name=event_data["artist_name"],
        venue_name=event_data["venue_name"],
        event_date=event_data["event_date"],
        sale_date=event_data["sale_date"],
        presale_date=event_data["presale_date"],
        url=event_data["url"],
        content_hash=generate_content_hash(event_data),
    )


def test_latest_command_lists_recent_events(db_session):
    db_session.add(sample_event("2026 Example Concert", "https://example.com/1", datetime(2026, 9, 1, tzinfo=timezone.utc)))
    db_session.commit()

    reply = handle_telegram_command("/latest", "123", db_session)

    assert reply.startswith("Latest concerts found")
    assert "Example Concert" in reply
    assert "Venue: Singapore Indoor Stadium" in reply
    assert "URL: https://example.com/1" in reply


def test_upcoming_command_lists_upcoming_events(db_session):
    db_session.add(sample_event("2028 Future Concert", "https://example.com/future", datetime(2028, 9, 1, tzinfo=timezone.utc)))
    db_session.commit()

    reply = handle_telegram_command("/upcoming", "123", db_session)

    assert reply.startswith("Upcoming concerts")
    assert "Future Concert" in reply
    assert "URL: https://example.com/future" in reply
