from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy import select

from app import crud
from app.models import Alert, Event
from app.services import notifications as notify
from app.services.telegram_payload import message_payload
from app.services.watchlist import add_watch_keyword, sale_reminder_matches
from app.services.event_detector import process_events
from app.services.sale_windows import reminder_sales


def test_long_unicode_alert_is_bounded_and_ticket_link_survives():
    event = Event(title="音" * 500, url="https://ticketmaster.sg/" + "x" * 900,
                  content_hash="x", event_date=datetime(2030, 1, 1, tzinfo=timezone.utc))
    payload = message_payload("123", notify.format_event_message(event))
    assert len(payload["text"].encode("utf-16-le")) // 2 <= 4096
    assert payload["reply_markup"]["inline_keyboard"][0][0]["url"] == event.url
    assert payload["link_preview_options"]["is_disabled"]


def test_past_sale_has_no_calendar_action_and_is_labelled():
    event = Event(title="Artist", url="https://example.com", content_hash="x",
                  sale_date=datetime(2026, 6, 5, tzinfo=timezone.utc))
    message = notify.format_event_message(event, now=datetime(2026, 10, 8, tzinfo=timezone.utc))
    assert "General sale started:" in message
    assert "Add ticket sale to calendar" not in message


def test_presale_reminds_once_and_withdrawn_window_cancels_retry(db_session, monkeypatch):
    now = datetime.now(timezone.utc)
    event = Event(title="Artist", url="https://example.com", content_hash="x",
                  presale_date=now + timedelta(minutes=30), sale_date=now + timedelta(days=3))
    db_session.add(event)
    crud.activate_telegram_subscriber(db_session, "123")
    add_watch_keyword(db_session, "123", "artist")
    db_session.commit()
    monkeypatch.setattr(notify, "settings", SimpleNamespace(telegram_bot_token="test", telegram_chat_ids=[]))
    send = Mock(return_value=False)
    monkeypatch.setattr(notify, "send_telegram_message_to_chat", send)
    matches = sale_reminder_matches(db_session, 1, now)
    assert len(matches) == 1 and matches[0].sale.kind == "presale"
    notify.send_sale_reminder_alerts(matches, 1, db_session)
    notify.send_sale_reminder_alerts(matches, 1, db_session)
    assert len(list(db_session.scalars(select(Alert)))) == 1
    assert "Presale starts" in send.call_args.args[1]
    event.presale_date = None
    db_session.commit()
    assert notify.deliver_pending_alerts(db_session, now=now + timedelta(minutes=10)) == 0
    assert db_session.scalar(select(Alert)).delivery_state == "cancelled"


def test_permanent_delivery_failure_stops_retrying(db_session, monkeypatch):
    event = Event(title="Artist", url="https://example.com", content_hash="x")
    db_session.add(event)
    crud.activate_telegram_subscriber(db_session, "123")
    db_session.commit()
    monkeypatch.setattr(notify, "settings", SimpleNamespace(telegram_bot_token="test", telegram_chat_ids=[]))
    monkeypatch.setattr(notify, "send_telegram_message_to_chat", Mock(return_value=None))
    notify.send_new_event_alerts([event], db_session)
    assert db_session.scalar(select(Alert)).delivery_state == "failed"
    assert notify.deliver_pending_alerts(db_session) == 0


def test_named_presales_have_distinct_stable_reminder_keys(db_session):
    now = datetime.now(timezone.utc)
    event = process_events(db_session, [dict(source_name="Ticketmaster Discovery Singapore",
        source_event_id="one", title="Artist", url="https://example.com", sale_windows=[
            dict(external_id="fan", name="Fan club", kind="presale", starts_at=now + timedelta(days=1), ends_at=None),
            dict(external_id="bank", name="Cardholder", kind="presale", starts_at=now + timedelta(days=2), ends_at=None),
        ])]).new_events[0]
    sales = reminder_sales(event)
    assert {s.name for s in sales} == {"Fan club", "Cardholder"}
    assert len({s.key(1) for s in sales}) == 2
    assert all(len(s.key(24)) <= 100 for s in sales)


def test_shorter_reminder_suppression_respects_configuration(monkeypatch):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(notify, "settings", SimpleNamespace(sale_reminder_hours=[24]))
    assert not notify._shorter_reminder_due(24, now + timedelta(minutes=30), now)
    monkeypatch.setattr(notify, "settings", SimpleNamespace(sale_reminder_hours=[24, 1]))
    assert notify._shorter_reminder_due(24, now + timedelta(minutes=30), now)


def test_telegram_permanent_and_temporary_responses(monkeypatch):
    response = Mock(status_code=403)
    monkeypatch.setattr(notify.requests, "post", Mock(return_value=response))
    assert notify._send_telegram_message_to_chat("https://example.com", "123", "Hello") is None
    response.status_code = 429
    response.raise_for_status.side_effect = notify.requests.HTTPError()
    assert notify._send_telegram_message_to_chat("https://example.com", "123", "Hello") is False
