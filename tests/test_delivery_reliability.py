from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import crud, scheduler
from app.models import Alert
from app.database import Base
from app.services import notifications as notify
from app.services.event_detector import process_events
from app.services.job_lock import source_check_lock
from app.services.telegram_commands import handle_telegram_command
from app.services.watchlist import add_watch_keyword, sale_reminder_matches


def event_data(**changes):
    data = dict(title="Artist concert", artist_name="Artist", venue_name="Venue",
                event_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
                sale_date=None, presale_date=None, url="https://example.com/show",
                source_name="Example")
    data.update(changes)
    return data


@pytest.fixture
def delivery(monkeypatch, db_session):
    monkeypatch.setattr(notify, "settings", SimpleNamespace(telegram_bot_token="fake", telegram_chat_ids=[]))
    # All delivery tests mock Telegram at its boundary.
    send = Mock(return_value=True)
    monkeypatch.setattr(notify, "send_telegram_message_to_chat", send)
    handle_telegram_command("/start", "123", db_session)
    return send


def test_failed_send_retries_without_another_event_change(db_session, delivery):
    event = process_events(db_session, [event_data()]).new_events[0]
    delivery.return_value = False
    assert notify.send_new_event_alerts([event], db_session) == 0
    alert = db_session.scalar(select(Alert))
    assert alert.delivery_state == "pending" and alert.sent_at is None
    assert process_events(db_session, [event_data()]).unchanged_events
    delivery.return_value = True
    assert notify.deliver_pending_alerts(db_session, now=notify._utc(alert.next_attempt_at)) == 1
    assert notify.deliver_pending_alerts(db_session, now=datetime.now(timezone.utc) + timedelta(hours=1)) == 0
    assert delivery.call_count == 2


def test_two_updates_and_reversion_each_notify(db_session, delivery):
    process_events(db_session, [event_data()])
    for venue in ("New venue", "Third venue", "Venue"):
        result = process_events(db_session, [event_data(venue_name=venue)])
        assert notify.send_updated_event_alerts(result.updated_events, db_session) == 1
        assert notify.send_updated_event_alerts(result.updated_events, db_session) == 0
    assert delivery.call_count == 3


def test_presale_change_and_equivalent_timezone(db_session):
    process_events(db_session, [event_data()])
    presale = datetime(2026, 12, 1, tzinfo=timezone.utc)
    result = process_events(db_session, [event_data(presale_date=presale)])
    assert notify._utc(result.updated_events[0].presale_date) == presale
    equivalent = presale.astimezone(timezone(timedelta(hours=8)))
    assert process_events(db_session, [event_data(presale_date=equivalent)]).unchanged_events


def test_claim_is_exclusive_and_expired_claim_can_recover(db_session, delivery):
    event = process_events(db_session, [event_data()]).new_events[0]
    notify.queue_event_alerts([event], "new_event", db_session)
    db_session.commit()
    alert = db_session.scalar(select(Alert))
    now = datetime.now(timezone.utc)
    assert notify.claim_alert(db_session, alert.id, now)
    assert notify.claim_alert(db_session, alert.id, now) is None
    assert notify.claim_alert(db_session, alert.id, now + timedelta(minutes=6))


@pytest.mark.parametrize("reason", ["stop", "unwatch", "expired", "rescheduled"])
def test_stale_reminders_are_cancelled(db_session, delivery, reason):
    now = datetime.now(timezone.utc)
    event = process_events(db_session, [event_data(sale_date=now + timedelta(minutes=30))]).new_events[0]
    add_watch_keyword(db_session, "123", "artist")
    db_session.commit()
    delivery.return_value = False
    notify.send_sale_reminder_alerts(sale_reminder_matches(db_session, 1, now), 1, db_session)
    if reason == "stop":
        handle_telegram_command("/stop", "123", db_session)
        handle_telegram_command("/start", "123", db_session)
    elif reason == "unwatch":
        handle_telegram_command("/unwatch artist", "123", db_session)
    elif reason == "rescheduled":
        event.sale_date = now + timedelta(days=1)
        db_session.commit()
    delivery.reset_mock()
    delivery.return_value = True
    retry_time = now + timedelta(hours=1) if reason == "expired" else now + timedelta(minutes=10)
    assert notify.deliver_pending_alerts(db_session, now=retry_time) == 0
    delivery.assert_not_called()
    assert db_session.scalar(select(Alert)).delivery_state == "cancelled"


def test_rescheduled_sale_gets_new_reminder(db_session, delivery):
    now = datetime.now(timezone.utc)
    event = process_events(db_session, [event_data(sale_date=now + timedelta(minutes=30))]).new_events[0]
    add_watch_keyword(db_session, "123", "artist")
    db_session.commit()
    assert notify.send_sale_reminder_alerts(sale_reminder_matches(db_session, 1, now), 1, db_session) == 1
    event.sale_date = now + timedelta(minutes=45)
    db_session.commit()
    assert notify.send_sale_reminder_alerts(sale_reminder_matches(db_session, 1, now), 1, db_session) == 1


def test_queue_failure_rolls_back_event_changes(monkeypatch, db_session, delivery):
    monkeypatch.setattr(scheduler, "settings", SimpleNamespace(send_alerts_on_first_run=True))
    monkeypatch.setattr(scheduler.LiveNationSGScraper, "fetch_events", lambda self: [event_data()])
    monkeypatch.setattr(scheduler, "queue_event_alerts", Mock(side_effect=RuntimeError("queue failed")))
    with pytest.raises(RuntimeError, match="queue failed"):
        scheduler.run_livenation_check(db_session)
    assert crud.count_events(db_session) == 0
    delivery.assert_not_called()


def test_source_lock_excludes_another_check(db_session):
    with source_check_lock(db_session.get_bind()) as acquired:
        assert acquired
        with source_check_lock(db_session.get_bind()) as second:
            assert not second
    with source_check_lock(db_session.get_bind()) as released:
        assert released


def test_explicit_empty_recipients_never_fall_back(monkeypatch):
    send = Mock()
    monkeypatch.setattr(notify, "settings", SimpleNamespace(telegram_bot_token="fake", telegram_chat_ids=["123"]))
    monkeypatch.setattr(notify, "_send_telegram_message_to_chat", send)
    assert notify.send_telegram_message("test", chat_ids=[]) == 0
    send.assert_not_called()


def test_independent_workers_cannot_claim_same_delivery(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'claims.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        event = process_events(db, [event_data()]).new_events[0]
        alert = Alert(event_id=event.id, chat_id="123", alert_type="new_event", message="test", delivery_state="pending")
        db.add(alert)
        db.commit()
        alert_id = alert.id
    barrier = Barrier(2)
    now = datetime.now(timezone.utc)
    def claim():
        with Session(engine) as db:
            barrier.wait(timeout=5)
            return notify.claim_alert(db, alert_id, now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(token is not None for token in results) == 1
    with source_check_lock(engine) as acquired:
        assert acquired
        with source_check_lock(engine) as other:
            assert not other
    engine.dispose()


def test_first_run_silent_then_update_is_queued(monkeypatch, db_session, delivery):
    monkeypatch.setattr(scheduler, "settings", SimpleNamespace(send_alerts_on_first_run=False, sale_reminder_hours=[]))
    fetch = Mock(return_value=[event_data()])
    monkeypatch.setattr(scheduler.LiveNationSGScraper, "fetch_events", fetch)
    assert scheduler.run_livenation_check(db_session).notifications_sent == 0
    assert db_session.scalar(select(Alert)) is None
    fetch.return_value = [event_data(venue_name="New venue")]
    assert scheduler.run_livenation_check(db_session).notifications_sent == 1
    assert db_session.scalar(select(Alert)).delivery_state == "sent"


def test_event_and_queued_delivery_roll_back_together(db_session, delivery):
    result = process_events(db_session, [event_data()], commit=False)
    notify.queue_event_alerts(result.new_events, "new_event", db_session)
    db_session.rollback()
    assert crud.count_events(db_session) == 0
    assert db_session.scalar(select(Alert)) is None
