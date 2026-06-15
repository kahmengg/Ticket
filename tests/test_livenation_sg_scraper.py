from datetime import datetime, timezone

from app.scrapers.livenation_sg import LiveNationSGScraper


def test_parse_api_document_normalizes_live_nation_event():
    scraper = LiveNationSGScraper()
    event = scraper._parse_api_document(
        {
            "name": "Example Tour Singapore",
            "eventDateUtc": "2026-06-20T09:00:00Z",
            "url": "/event/example-tour-singapore-tickets-edp123",
            "venue": {"name": "The Star Theatre, Singapore"},
            "lineup": [{"name": "Example Artist", "isPrimary": True, "type": "headline"}],
            "tickets": [
                {"type": "Live Nation Presale", "validFromUtc": "2026-04-14T06:00:00Z"},
                {"type": "General Onsale", "validFromUtc": "2026-04-15T06:00:00Z"},
            ],
        }
    )

    assert event == {
        "title": "Example Tour Singapore",
        "artist_name": "Example Artist",
        "venue_name": "The Star Theatre, Singapore",
        "event_date": datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
        "sale_date": datetime(2026, 4, 15, 6, 0, tzinfo=timezone.utc),
        "presale_date": datetime(2026, 4, 14, 6, 0, tzinfo=timezone.utc),
        "url": "https://www.livenation.sg/event/example-tour-singapore-tickets-edp123",
        "source_name": "Live Nation Singapore",
    }
