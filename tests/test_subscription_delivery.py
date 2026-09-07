from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app import crud
from app.api import routes
from app.models import Event
from app.services import notifications
from app.services.telegram_commands import handle_telegram_command
from app.services.watchlist import add_watch_keyword, sale_reminder_matches


@pytest.mark.parametrize("text", ["/help", "/watchlist", "/watch artist", "hello", ""])
def test_webhook_messages_do_not_resubscribe(monkeypatch, db_session, text):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(telegram_webhook_secret="secret"))
    monkeypatch.setattr(routes, "send_telegram_message_to_chat", Mock(return_value=True))
    handle_telegram_command("/start", "123", db_session)
    handle_telegram_command("/stop", "123", db_session)
    routes.telegram_webhook(
        {"message": {"chat": {"id": 123}, "text": text}},
        db=db_session, x_telegram_bot_api_secret_token="secret",
    )
    assert crud.telegram_subscription_state(db_session, "123") is False
    handle_telegram_command("/start@ticketbot", "123", db_session)
    assert crud.telegram_subscription_state(db_session, "123") is True


def test_stop_blocks_all_delivery_and_preserves_watchlist(monkeypatch, db_session):
    monkeypatch.setattr(notifications, "settings", SimpleNamespace(
        telegram_bot_token="fake", telegram_chat_ids=["123"],
    ))
    # Mock the delivery boundary so tests never send real Telegram messages.
    send = Mock(return_value=True)
    monkeypatch.setattr(notifications, "send_telegram_message_to_chat", send)
    now = datetime.now(timezone.utc)
    event = Event(title="Artist concert", url="https://example.com/event",
                  sale_date=now + timedelta(minutes=30), content_hash="hash")
    db_session.add(event)
    handle_telegram_command("/start", "123", db_session)
    add_watch_keyword(db_session, "123", "artist")
    db_session.commit()
    matches = sale_reminder_matches(db_session, 1, now=now)
    assert len(matches) == 1

    handle_telegram_command("/stop", "123", db_session)
    assert notifications.get_notification_chat_ids(db_session) == []
    assert sale_reminder_matches(db_session, 1, now=now) == []
    assert notifications.send_new_event_alerts([event], db_session) == 0
    assert notifications.send_updated_event_alerts([event], db_session) == 0
    # Matches computed before /stop must also be rejected at delivery time.
    assert notifications.send_sale_reminder_alerts(matches, 1, db_session) == 0
    send.assert_not_called()
    assert len(crud.list_active_watchlist_keywords(db_session, "123")) == 1

    handle_telegram_command("/start", "123", db_session)
    assert notifications.send_sale_reminder_alerts(matches, 1, db_session) == 1
    send.assert_called_once()


def test_new_chat_requires_start_and_metadata_updates_preserve_state(db_session):
    crud.upsert_telegram_subscriber(db_session, "123", username="first")
    assert crud.telegram_subscription_state(db_session, "123") is False
    handle_telegram_command("/start", "123", db_session)
    subscriber = crud.upsert_telegram_subscriber(db_session, "123", username="renamed")
    assert subscriber.username == "renamed"
    assert subscriber.is_active is True
