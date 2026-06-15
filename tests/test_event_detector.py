from datetime import datetime, timezone

from app.services.event_detector import generate_content_hash, process_events


def sample_event(**overrides):
    event = {
        "title": "Example Artist",
        "artist_name": "Example Artist",
        "venue_name": "National Stadium",
        "event_date": datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        "sale_date": datetime(2026, 7, 1, 2, 0, tzinfo=timezone.utc),
        "presale_date": None,
        "url": "https://example.com/events/example-artist",
        "source_name": "Example Source",
    }
    event.update(overrides)
    return event


def test_content_hash_is_stable():
    assert generate_content_hash(sample_event()) == generate_content_hash(sample_event())


def test_detects_new_event(db_session):
    result = process_events(db_session, [sample_event()])

    assert len(result.new_events) == 1
    assert len(result.updated_events) == 0
    assert len(result.unchanged_events) == 0


def test_detects_unchanged_event(db_session):
    process_events(db_session, [sample_event()])
    result = process_events(db_session, [sample_event()])

    assert len(result.new_events) == 0
    assert len(result.updated_events) == 0
    assert len(result.unchanged_events) == 1


def test_detects_changed_event(db_session):
    process_events(db_session, [sample_event()])
    result = process_events(db_session, [sample_event(sale_date=datetime(2026, 7, 2, 2, 0, tzinfo=timezone.utc))])

    assert len(result.new_events) == 0
    assert len(result.updated_events) == 1
    assert len(result.unchanged_events) == 0
