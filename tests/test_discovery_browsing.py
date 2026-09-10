from datetime import datetime, timedelta, timezone

from sqlalchemy import event as sqlalchemy_event

from app import crud
from app.models import Event
from app.services.event_detector import process_events

NOW = datetime(2027, 1, 1, tzinfo=timezone.utc)


def observation(title, source="Live Nation Singapore", **extra):
    return dict(title=title, source_name=source, url=f"https://example.com/{source}/{title}",
                event_date=NOW + timedelta(days=5), venue_name="Venue", **extra)


def test_equal_batch_times_sort_by_title_and_imports_last(db_session):
    process_events(db_session, [observation("Zulu"), observation("Alpha")], discovery_at=NOW)
    process_events(db_session, [observation("Aardvark")], initial_import=True, discovery_at=NOW + timedelta(days=1))
    events = crud.list_latest_events(db_session)
    assert [e.title for e in events] == ["Alpha", "Zulu", "Aardvark"]
    assert events[0].discovered_at == events[1].discovered_at


def test_provider_and_details_updates_do_not_reset_discovery(db_session):
    process_events(db_session, [observation("Artist")], discovery_at=NOW)
    process_events(db_session, [observation("Artist", "Ticketmaster Singapore", price_summary="SGD 100")], discovery_at=NOW + timedelta(days=1))
    events = crud.list_latest_events(db_session)
    assert len(events) == 1
    assert events[0].discovered_at.replace(tzinfo=timezone.utc) == NOW


def test_upcoming_filters_past_performance_even_with_future_sale(db_session):
    for title, date, status in [("Past", NOW - timedelta(days=1), "active"),
                                ("Undated", None, "active"), ("Future", NOW + timedelta(days=1), "active"),
                                ("Cancelled", NOW + timedelta(days=2), "cancelled")]:
        db_session.add(Event(title=title, url="https://example.com", content_hash="x", event_date=date,
                             sale_date=NOW + timedelta(hours=1), status=status))
    db_session.commit()
    assert [e.title for e in crud.list_upcoming_events(db_session, NOW)] == ["Future", "Undated"]


def test_pages_clamp_and_exclude_newer_imports(db_session):
    for i in range(12):
        db_session.add(Event(title=f"Artist {i:02}", url="https://example.com", content_hash="x", first_seen_at=NOW))
    db_session.add(Event(title="New", url="https://example.com", content_hash="x", first_seen_at=NOW + timedelta(hours=1)))
    db_session.commit()
    events, total, page, pages = crud.browse_events(db_session, "latest", NOW, NOW, 99)
    assert (total, page, pages, len(events)) == (12, 2, 3, 2)


def test_browsing_uses_count_and_limited_query_without_relationship_loads(db_session):
    for i in range(12):
        db_session.add(Event(title=f"Show {i}", url="https://example.com", content_hash="x", first_seen_at=NOW))
    db_session.commit()
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    engine = db_session.get_bind()
    sqlalchemy_event.listen(engine, "before_cursor_execute", record)
    try:
        events, total, _, _ = crud.browse_events(db_session, "latest", NOW, NOW)
        assert len(events) == 5 and total == 12
        assert len(statements) == 2
        assert "LIMIT" in statements[1]
        assert all("source_listings" not in statement for statement in statements)
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", record)
