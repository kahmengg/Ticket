from unittest.mock import Mock

import pytest
import requests

from app.scrapers.ticketmaster_api import TicketmasterAPIScraper
from app.scrapers.ticketmaster_sg import SourceFetchError


def event():
    return dict(id="api-1", name="Artist show", url="https://ticketmaster.sg/activity/detail/show",
        dates=dict(start=dict(dateTime="2027-01-01T12:00:00Z"), status=dict(code="canceled")),
        sales=dict(public=dict(startDateTime="2026-12-01T04:00:00Z"), presales=[
            dict(name="Artist", startDateTime="2026-11-30T04:00:00Z")]),
        priceRanges=[dict(currency="SGD", min=100, max=200)],
        _embedded=dict(venues=[dict(name="Venue", country=dict(countryCode="SG"))],
                       attractions=[dict(name="Artist")]))


def test_official_fields_and_tbd_dates():
    scraper = TicketmasterAPIScraper("private")
    data = event()
    parsed = scraper.parse_event(data)
    assert parsed["status"] == "cancelled"
    assert parsed["source_event_id"] == "api-1"
    assert parsed["price_summary"] == "SGD 100–200"
    assert len(parsed["sale_windows"]) == 2
    data["dates"]["start"]["timeTBA"] = True
    data["sales"]["public"]["startTBD"] = True
    parsed = scraper.parse_event(data)
    assert parsed["event_date"] is None and parsed["sale_date"] is None


def test_request_uses_singapore_filter_and_bounded_pagination(monkeypatch):
    request = Mock(side_effect=[Mock(status_code=200, json=lambda: {
        "page": {"totalPages": 2}, "_embedded": {"events": [event()]}})] * 2)
    monkeypatch.setattr(requests, "get", request)
    monkeypatch.setattr("app.scrapers.ticketmaster_api.time.sleep", lambda _: None)
    assert len(TicketmasterAPIScraper("private").fetch_events()) == 1
    assert request.call_count == 2
    assert request.call_args.kwargs["params"]["countryCode"] == "SG"
    assert request.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_errors_never_expose_response_or_key(monkeypatch, status):
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(status_code=status, text="private")))
    with pytest.raises(SourceFetchError, match=f"HTTP {status}") as error:
        TicketmasterAPIScraper("private").fetch_events()
    assert "private" not in str(error.value)


def test_transport_error_does_not_expose_key(monkeypatch):
    monkeypatch.setattr(requests, "get", Mock(side_effect=requests.ConnectionError("apikey=private")))
    with pytest.raises(SourceFetchError, match="connection failed") as error:
        TicketmasterAPIScraper("private").fetch_events()
    assert "private" not in str(error.value)


def test_no_coverage_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(status_code=200,
        json=lambda: {"page": {"totalPages": 0}})))
    with pytest.raises(SourceFetchError, match="coverage is unverified"):
        TicketmasterAPIScraper("private").fetch_events()
