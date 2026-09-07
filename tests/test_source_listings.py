from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import Event, SourceListing
from app.schemas import EventRead
from app.services.event_detector import process_events
from app.services.notifications import format_event_message


WHEN = datetime(2027, 1, 1, 12, tzinfo=timezone.utc)


def observation(source="Live Nation Singapore", **changes):
    data = dict(source_name=source, title="Artist World Tour", artist_name="Artist",
                venue_name="National Stadium", event_date=WHEN, sale_date=None, presale_date=None,
                url="https://livenation.sg/event/artist" if source == "Live Nation Singapore" else "https://ticketmaster.sg/activity/detail/artist")
    data.update(changes)
    return data


def test_two_sources_in_one_batch_make_one_event(db_session):
    result = process_events(db_session, [observation(), observation("Ticketmaster Singapore")])
    assert len(result.new_events) == 1
    event = result.new_events[0]
    assert len(event.listings) == 2
    assert event.url.startswith("https://livenation.sg")
    assert event.field_provenance["url"] in {listing.id for listing in event.listings}
    serialized = EventRead.model_validate(event).model_dump()
    assert {listing["source_name"] for listing in serialized["listings"]} == {"Live Nation Singapore", "Ticketmaster Singapore"}
    assert "Ticketmaster Singapore: https://ticketmaster.sg/activity/detail/artist" in format_event_message(event)


def test_adding_equivalent_source_does_not_send_an_update(db_session):
    original = process_events(db_session, [observation()]).new_events[0]
    result = process_events(db_session, [observation("Ticketmaster Singapore")])
    assert result.new_events == result.updated_events == []
    assert result.unchanged_events[0].id == original.id
    assert original.revision == 1


@pytest.mark.parametrize("reverse", [False, True])
def test_field_priority_does_not_depend_on_scrape_order(db_session, reverse):
    ln = observation(sale_date=WHEN - timedelta(days=30))
    tm = observation("Ticketmaster Singapore", sale_date=WHEN - timedelta(days=20),
                     price_summary="SGD 100–200", currency="SGD")
    result = process_events(db_session, [tm, ln] if reverse else [ln, tm])
    event = result.new_events[0]
    assert event.sale_date.replace(tzinfo=timezone.utc) == tm["sale_date"]
    assert event.price_summary == "SGD 100–200"
    chosen = next(item for item in event.listings if item.id == event.field_provenance["sale_date"])
    assert chosen.source_name == "Ticketmaster Singapore"
    for scraped in [ln, tm, ln, tm]:
        assert process_events(db_session, [scraped]).updated_events == []


def test_multiple_performances_can_share_url(db_session):
    first = observation("Ticketmaster Singapore", source_event_id="show-1")
    second = observation("Ticketmaster Singapore", source_event_id="show-2", event_date=WHEN + timedelta(days=1))
    result = process_events(db_session, [first, second])
    assert len(result.new_events) == 2
    assert len({event.url for event in result.new_events}) == 1
    # A stable performance ID preserves identity when its date changes.
    first["event_date"] = WHEN + timedelta(days=2)
    changed = process_events(db_session, [first])
    assert len(changed.updated_events) == 1
    assert db_session.scalar(select(func.count(Event.id))) == 2


def test_shared_url_without_performance_ids_is_rejected(db_session):
    with pytest.raises(ValueError, match="source_event_id"):
        process_events(db_session, [observation(), observation(event_date=WHEN + timedelta(days=1))])
    db_session.rollback()
    assert db_session.scalar(select(func.count(Event.id))) == 0


@pytest.mark.parametrize("changes", [
    {"venue_name": "Another venue"}, {"event_date": WHEN + timedelta(hours=1)},
    {"event_date": None}, {"title": "Artist Unrelated Show"}, {"artist_name": "Another Artist"},
])
def test_uncertain_matches_stay_separate(db_session, changes):
    process_events(db_session, [observation()])
    assert len(process_events(db_session, [observation("Ticketmaster Singapore", **changes)]).new_events) == 1


def test_ambiguous_candidates_are_not_merged(db_session):
    process_events(db_session, [observation(source_event_id="a"), observation(source_event_id="b")])
    result = process_events(db_session, [observation("Ticketmaster Singapore")])
    assert len(result.new_events) == 1
    assert db_session.scalar(select(func.count(Event.id))) == 3


def test_missing_fields_preserve_known_values_and_record_missing_observation(db_session):
    sale = WHEN - timedelta(days=30)
    event = process_events(db_session, [observation(sale_date=sale)]).new_events[0]
    result = process_events(db_session, [observation(sale_date=None)])
    assert result.updated_events == []
    assert event.sale_date.replace(tzinfo=timezone.utc) == sale
    assert event.listings[0].observed_data["sale_date"] is None


def test_named_sale_windows_are_preserved_per_source(db_session):
    windows = [dict(external_id="fan", name="Fan club presale", kind="presale",
                    starts_at=WHEN - timedelta(days=20), ends_at=WHEN - timedelta(days=19)),
               dict(external_id="public", name="General sale", kind="general",
                    starts_at=WHEN - timedelta(days=18), ends_at=None)]
    event = process_events(db_session, [observation("Ticketmaster Singapore", sale_windows=windows)]).new_events[0]
    assert len(event.listings[0].sale_windows) == 2
    assert event.presale_date.replace(tzinfo=timezone.utc) == windows[0]["starts_at"]
    assert event.sale_date.replace(tzinfo=timezone.utc) == windows[1]["starts_at"]
    assert process_events(db_session, [observation("Ticketmaster Singapore", sale_windows=windows)]).updated_events == []


def test_compatible_title_variations_merge(db_session):
    process_events(db_session, [observation()])
    result = process_events(db_session, [observation("Ticketmaster Singapore", title="2027 Artist World Tour in Singapore")])
    assert result.new_events == []
    assert db_session.scalar(select(func.count(SourceListing.id))) == 2


def test_price_currency_never_comes_from_another_source(db_session):
    event = process_events(db_session, [observation(price_summary="100", currency="USD"),
                                       observation("Ticketmaster Singapore", price_summary="200", currency=None)]).new_events[0]
    assert event.price_summary == "200"
    assert event.currency is None
    assert "currency" not in event.field_provenance


def test_named_presale_replaces_generic_fallback(db_session):
    event = process_events(db_session, [observation(presale_date=WHEN - timedelta(days=30))]).new_events[0]
    named = dict(external_id="fan-club", name="Fan club", kind="presale",
                 starts_at=WHEN - timedelta(days=20), ends_at=None)
    process_events(db_session, [observation(sale_windows=[named])])
    assert [window.external_id for window in event.listings[0].sale_windows] == ["fan-club"]
    assert event.presale_date.replace(tzinfo=timezone.utc) == named["starts_at"]
