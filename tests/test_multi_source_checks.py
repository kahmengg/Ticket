from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app import crud, scheduler
from app.models import Alert, Event, Source
from app.services import notifications


def item(source, title="Artist show", **extra):
    data = dict(source_name=source, title=title, artist_name="Artist", venue_name="Venue",
                event_date=datetime(2027, 1, 1, 12, tzinfo=timezone.utc), sale_date=None, presale_date=None,
                url="https://livenation.sg/event/show" if source == "Live Nation Singapore" else "https://ticketmaster.sg/activity/detail/show")
    data.update(extra)
    return data


def scraper(name, data=None, failure=None, errors=None):
    return SimpleNamespace(source_name=name, base_url="https://example.com", warnings=[], errors=errors or [],
                           fetch_events=Mock(return_value=data, side_effect=failure))


@pytest.fixture
def configured(monkeypatch, db_session):
    monkeypatch.setattr(scheduler, "settings", SimpleNamespace(send_alerts_on_first_run=False, sale_reminder_hours=[]))
    monkeypatch.setattr(notifications, "settings", SimpleNamespace(telegram_bot_token="fake", telegram_chat_ids=[]))
    send = Mock(return_value=True)
    monkeypatch.setattr(notifications, "send_telegram_message_to_chat", send)
    crud.activate_telegram_subscriber(db_session, "123")
    db_session.commit()
    return send


def test_each_source_seeds_silently_then_alerts_new_events(db_session, configured):
    ln = scraper("Live Nation Singapore", [item("Live Nation Singapore")])
    tm = scraper("Ticketmaster Singapore", [item("Ticketmaster Singapore", title="Different show")])
    scheduler.run_event_check(db_session, scrapers=[ln])
    result = scheduler.run_event_check(db_session, scrapers=[ln, tm])
    assert result.notifications_sent == 0
    assert result.source_results[1]["seeded"] is True
    tm.fetch_events.return_value = [item("Ticketmaster Singapore", title="New concert", url="https://ticketmaster.sg/activity/detail/new")]
    result = scheduler.run_event_check(db_session, scrapers=[ln, tm])
    assert result.notifications_sent == 1
    configured.assert_called_once()


def test_failed_source_does_not_discard_other_source(db_session, configured):
    result = scheduler.run_event_check(db_session, scrapers=[
        scraper("Live Nation Singapore", failure=RuntimeError("private failure text")),
        scraper("Ticketmaster Singapore", [item("Ticketmaster Singapore")]),
    ])
    assert len(result.new_events) == 1
    assert [source["status"] for source in result.source_results] == ["failed", "ok"]
    assert result.source_results[0]["error"] == "RuntimeError"
    ln = db_session.scalar(select(Source).where(Source.name == "Live Nation Singapore"))
    assert ln.baseline_at is None and ln.last_success_at is None


def test_processing_failure_isolated_and_partial_run_does_not_finish_baseline(db_session, configured):
    result = scheduler.run_event_check(db_session, scrapers=[
        scraper("Live Nation Singapore", [dict(source_name="Live Nation Singapore")]),
        scraper("Ticketmaster Singapore", [item("Ticketmaster Singapore")], errors=["A detail page failed"]),
    ])
    assert [source["status"] for source in result.source_results] == ["failed", "partial"]
    assert crud.count_events(db_session) == 1
    assert db_session.scalar(select(Source).where(Source.name == "Ticketmaster Singapore")).baseline_at is None


def test_two_sources_change_same_event_only_one_revision_and_alert(db_session, configured):
    ln = scraper("Live Nation Singapore", [item("Live Nation Singapore")])
    tm = scraper("Ticketmaster Singapore", [item("Ticketmaster Singapore")])
    scheduler.run_event_check(db_session, scrapers=[ln, tm])
    ln.fetch_events.return_value = [item("Live Nation Singapore", venue_name="New venue")]
    tm.fetch_events.return_value = [item("Ticketmaster Singapore", price_summary="SGD 200", currency="SGD")]
    result = scheduler.run_event_check(db_session, scrapers=[ln, tm])
    assert len(result.updated_events) == 1
    assert result.updated_events[0].revision == 2
    assert result.notifications_sent == 1
    assert len(list(db_session.scalars(select(Alert)))) == 1


def test_empty_result_is_failure_not_successful_baseline(db_session, configured):
    result = scheduler.run_event_check(db_session, scrapers=[scraper("Ticketmaster Singapore", [])])
    assert result.source_results[0]["status"] == "failed"
    assert db_session.scalar(select(Source)).baseline_at is None


def test_migration_hash_change_does_not_create_false_alert(db_session, configured):
    ln = scraper("Live Nation Singapore", [item("Live Nation Singapore")])
    scheduler.run_event_check(db_session, scrapers=[ln])
    db_session.scalar(select(Event)).content_hash = "old-algorithm"
    db_session.commit()
    result = scheduler.run_event_check(db_session, scrapers=[ln])
    assert result.updated_events == []
    configured.assert_not_called()
