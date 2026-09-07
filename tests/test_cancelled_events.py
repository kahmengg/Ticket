from datetime import datetime, timedelta, timezone

import pytest

from app import crud
from app.models import Event
from app.services.watchlist import add_watch_keyword, sale_reminder_matches
from app.services.notifications import format_event_message
from app.services.source_matching import normalized_venue


@pytest.mark.parametrize("status", ["cancelled", "postponed"])
def test_inactive_performances_are_not_upcoming_or_reminded(db_session, status):
    now = datetime.now(timezone.utc)
    event = Event(title="Artist", url="https://example.com/show", status=status,
                  content_hash="test", event_date=now + timedelta(days=1),
                  sale_date=now + timedelta(minutes=30), price_summary="SGD 100")
    db_session.add(event)
    crud.activate_telegram_subscriber(db_session, "123")
    add_watch_keyword(db_session, "123", "Artist")
    db_session.commit()
    assert crud.list_upcoming_events(db_session, now) == []
    assert crud.list_upcoming_events_limited(db_session, now) == []
    assert sale_reminder_matches(db_session, 1, now) == []
    assert f"Status: {status}" in format_event_message(event)
    assert "Prices: SGD 100" in format_event_message(event)


def test_venue_country_suffix_preserves_singapore_venue_name():
    assert normalized_venue("National Stadium, Singapore") == normalized_venue("National Stadium")
    assert normalized_venue("Singapore Indoor Stadium") == "singapore indoor stadium"
