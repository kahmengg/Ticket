from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.scrapers.ticketmaster_sg import SourceFetchError, TicketmasterSGScraper, parse_local_datetime

FIXTURES = Path(__file__).parent / "fixtures" / "ticketmaster"


def parse(name):
    return TicketmasterSGScraper().parse_detail((FIXTURES / f"{name}.html").read_text(encoding="utf-8"),
                                               f"https://ticketmaster.sg/activity/detail/{name}")


def test_multi_performance_page_has_stable_ids_and_correct_utc_times():
    events = parse("26sg_theweeknd")
    assert [event["source_event_id"] for event in events] == ["26sg_theweeknd:3421", "26sg_theweeknd:3422"]
    assert events[0]["event_date"] == datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    assert events[0]["url"] == events[1]["url"]
    assert events[0]["sale_date"] == datetime(2026, 5, 21, 4, tzinfo=timezone.utc)
    assert len(events[0]["sale_windows"]) == 4


def test_single_date_presales_and_category_prices():
    event = parse("26sg_itzy")[0]
    assert event["event_date"] == datetime(2026, 10, 3, 10, tzinfo=timezone.utc)
    assert event["sale_date"] == datetime(2026, 7, 2, 8, tzinfo=timezone.utc)
    assert len(event["sale_windows"]) == 4
    assert event["price_summary"].startswith("SGD 158–386")


def test_postponed_page_without_status_column():
    assert parse("26sg_postmalone")[0]["status"] == "postponed"


def test_membership_eligibility_date_does_not_replace_actual_presale():
    event = parse("26sg_byeonwooseok")[0]
    assert event["presale_date"] == datetime(2026, 7, 9, 6, tzinfo=timezone.utc)


@pytest.mark.parametrize("text,expected", [
    ("Mon, 15th June 2026 at 10AM", datetime(2026, 6, 15, 2, tzinfo=timezone.utc)),
    ("03 Oct 2026 (Sat.) 06:00 pm", datetime(2026, 10, 3, 10, tzinfo=timezone.utc)),
    ("31 Feb 2026 at 12pm", None), ("3 Oct 2026", None), ("10am", None),
])
def test_date_parser_never_invents_missing_dates(text, expected):
    assert parse_local_datetime(text) == expected


def test_listing_deduplicates_detail_pages_and_rejects_external_links():
    scraper = TicketmasterSGScraper()
    assert scraper.listing_urls('<div class="listing-container"><a href="/activity/detail/show">1</a><a href="/activity/detail/show">2</a></div>') == ['https://ticketmaster.sg/activity/detail/show']
    with pytest.raises(SourceFetchError):
        scraper.detail_url("https://evil.example/activity/detail/show")


def test_changed_layout_is_reported_as_failure():
    with pytest.raises(SourceFetchError):
        TicketmasterSGScraper().parse_detail("<h1>Access denied</h1>", "https://ticketmaster.sg/activity/detail/show")
