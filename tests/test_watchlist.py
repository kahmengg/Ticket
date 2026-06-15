from datetime import datetime, timedelta, timezone

from app import crud
from app.models import Event
from app.services.event_detector import generate_content_hash
from app.services.watchlist import (
    add_watch_keyword,
    event_matches_keyword,
    matching_events_for_keyword,
    normalize_keyword,
    sale_reminder_matches,
)


def sample_event(title: str, sale_date=None):
    event_data = {
        "title": title,
        "artist_name": title,
        "venue_name": "Singapore Indoor Stadium",
        "event_date": datetime(2026, 11, 28, 10, 0, tzinfo=timezone.utc),
        "sale_date": sale_date,
        "presale_date": None,
        "url": f"https://example.com/{title}",
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


def test_watch_keyword_matches_case_and_spacing_variants():
    keyword = normalize_keyword("big bang")
    event = sample_event("2026 BIGBANG WORLD TOUR IN SINGAPORE")

    assert event_matches_keyword(event, keyword)


def test_matching_events_for_keyword_finds_existing_event(db_session):
    db_session.add(sample_event("2026 BABYMONSTER WORLD TOUR IN SINGAPORE"))
    db_session.commit()

    matches = matching_events_for_keyword(db_session, "baby monster")

    assert len(matches) == 1
    assert "BABYMONSTER" in matches[0].title


def test_sale_reminder_matches_only_matching_watchlist(db_session):
    now = datetime(2026, 6, 10, 4, 0, tzinfo=timezone.utc)
    event = sample_event("2026 BABYMONSTER WORLD TOUR IN SINGAPORE", sale_date=now + timedelta(hours=1))
    db_session.add(event)
    add_watch_keyword(db_session, "123", "baby monster")
    add_watch_keyword(db_session, "456", "coldplay")
    db_session.commit()

    matches = sale_reminder_matches(db_session, 1, now=now)

    assert [(match.chat_id, match.keyword) for match in matches] == [("123", "baby monster")]


def test_broad_watch_keyword_is_rejected(db_session):
    try:
        add_watch_keyword(db_session, "123", "concert")
    except ValueError as exc:
        assert "too broad" in str(exc)
    else:
        raise AssertionError("Expected broad keyword to be rejected")
