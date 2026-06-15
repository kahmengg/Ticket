from datetime import datetime, timezone

from app import crud
from app.models import Event, Source
from app.services.event_detector import generate_content_hash
from app.services.notifications import format_event_message


def test_format_event_message_removes_leading_year_and_adds_calendar_link():
    event = Event(
        title="2026-27 BABYMONSTER WORLD TOUR [춤 (CHOOM)] IN SINGAPORE",
        artist_name="BABYMONSTER",
        venue_name="Singapore Indoor Stadium",
        event_date=datetime(2026, 11, 28, 10, 0, tzinfo=timezone.utc),
        sale_date=datetime(2026, 6, 11, 4, 0, tzinfo=timezone.utc),
        presale_date=None,
        url="https://www.livenation.sg/event/babymonster",
        content_hash="hash",
    )

    message = format_event_message(event)

    assert message.startswith("BABYMONSTER WORLD TOUR [춤 (CHOOM)] IN SINGAPORE")
    assert "New event detected" not in message
    assert "Title:" not in message
    assert "Venue: Singapore Indoor Stadium" in message
    assert "Event date: 2026-11-28T10:00:00" in message
    assert "Sale date: 2026-06-11T04:00:00" in message
    assert "Add concert to calendar: https://calendar.google.com/calendar/render?" in message
    assert "Add ticket sale to calendar: https://calendar.google.com/calendar/render?" in message
    assert "Ticket+sale%3A+BABYMONSTER" in message


def test_alert_exists_after_create_alert(db_session):
    source = Source(name="Example Source", base_url="https://example.com", source_type="official")
    db_session.add(source)
    db_session.flush()

    event_data = {
        "title": "Example Artist",
        "artist_name": "Example Artist",
        "venue_name": "National Stadium",
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

    assert not crud.alert_exists(db_session, event.id, "new_event", "123")
    crud.create_alert(db_session, event.id, "new_event", "123", "message")

    assert crud.alert_exists(db_session, event.id, "new_event", "123")
