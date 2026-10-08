from datetime import datetime, timezone

from app.services.event_detector import process_events
from app.services.event_presentation import status_text
from app.services.notifications import format_event_message
from app.scrapers.ticketmaster_api import TicketmasterAPIScraper


def observation(**extra):
    data = dict(source_name="Ticketmaster Discovery Singapore", source_event_id="one", title="Artist: Tour!",
                venue_name="Venue", url="https://example.com/one", sale_date=datetime(2030, 1, 1, tzinfo=timezone.utc))
    return {**data, **extra}


def test_cosmetic_changes_do_not_alert_but_real_changes_explain_why(db_session):
    process_events(db_session, [observation()])
    assert not process_events(db_session, [observation(title="Artist Tour", url="https://example.com/two")]).updated_events
    result = process_events(db_session, [observation(venue_name="New venue")])
    assert "Changed: venue" in format_event_message(result.updated_events[0], "event_updated")


def test_explicit_withdrawal_clears_and_missing_extraction_preserves(db_session):
    event = process_events(db_session, [observation()]).new_events[0]
    process_events(db_session, [observation(sale_date=None)])
    assert event.sale_date is not None
    process_events(db_session, [observation(sale_date=None, clear_fields=["sale_date"],
        sale_windows=[], complete_sale_kinds=["general"])])
    assert event.sale_date is None and not event.listings[0].sale_windows
    process_events(db_session, [observation(sale_date=None)])
    assert event.sale_date is None


def test_future_offsale_is_not_presented_as_unavailable(db_session):
    event = process_events(db_session, [observation(status="unavailable")]).new_events[0]
    assert status_text(event, datetime(2029, 1, 1, tzinfo=timezone.utc)) == "General sale not open yet"


def test_api_marks_explicit_tbd_and_empty_presales_as_withdrawals():
    row = dict(id="one", name="Artist", url="https://example.com", dates={"start":{"timeTBA":True}},
               sales={"public":{"startTBD":True}, "presales":[]},
               _embedded={"venues":[{"name":"Venue", "country":{"countryCode":"SG"}}]})
    parsed = TicketmasterAPIScraper("unused").parse_event(row)
    assert set(parsed["clear_fields"]) == {"event_date", "sale_date", "presale_date"}
    assert set(parsed["complete_sale_kinds"]) == {"general", "presale"}
