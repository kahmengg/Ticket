from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.models import Event
from app.services import telegram_browsing as browsing, notifications

NOW = datetime(2027, 1, 1, tzinfo=timezone.utc)
STAMP = int(NOW.timestamp())


def seed(db, count=12):
    for i in range(count):
        db.add(Event(title=f"Artist {i:02}", content_hash="x", url="https://example.com/show",
                     first_seen_at=NOW - timedelta(days=1), event_date=NOW + timedelta(days=1)))
    db.commit()


def test_buttons_bound_to_chat_message_and_expiry():
    data = browsing.button_data("latest", 1, STAMP, 123, 456, "secret")
    assert len(data.encode()) <= 64
    assert browsing.read_button(data, 123, 456, "secret", STAMP) == ("latest", "1", STAMP)
    for chat, message, time in [(124, 456, STAMP), (123, 457, STAMP), (123, 456, STAMP + browsing.TTL)]:
        with pytest.raises(ValueError):
            browsing.read_button(data, chat, message, "secret", time)
    with pytest.raises(ValueError):
        browsing.read_button(data.replace(":1:", ":2:"), 123, 456, "secret", STAMP)


def test_first_last_empty_pages_and_import_group(db_session):
    seed(db_session)
    content, page, pages = browsing.page_content(db_session, "latest", 0, STAMP, NOW)
    assert "Page 1 of 3" in content["text"] and "Previously imported" in content["text"]
    assert len(content["entities"]) == 5
    keys = browsing.keyboard("latest", page, pages, STAMP, 123, 456, "secret")
    assert [x["text"] for row in keys["inline_keyboard"] for x in row] == ["Next", "Refresh"]
    content, page, pages = browsing.page_content(db_session, "latest", 2, STAMP, NOW)
    assert "Page 3 of 3" in content["text"] and len(content["entities"]) == 2
    content, _, _ = browsing.page_content(db_session, "upcoming", 0, STAMP, NOW + timedelta(days=2))
    assert "No concerts found" in content["text"]


def test_long_unicode_messages_keep_complete_links(db_session):
    seed(db_session, 5)
    for e in db_session.query(Event):
        e.title = "🎵" * 500
        e.venue_name = "V" * 255
        e.price_summary = "P" * 5000
        e.url = "https://example.com/" + "a" * 900
    db_session.commit()
    content, _, _ = browsing.page_content(db_session, "latest", 0, STAMP, NOW)
    encoded = content["text"].encode("utf-16-le")
    assert len(encoded) // 2 <= 4096
    for entity in content["entities"]:
        assert encoded[entity["offset"] * 2:(entity["offset"] + entity["length"]) * 2].decode("utf-16-le") == "Tickets"
        assert len(entity["url"]) > 900


def test_send_then_attach_signed_controls(db_session, monkeypatch):
    seed(db_session)
    api = Mock(side_effect=[{"message_id": 456}, True])
    monkeypatch.setattr(browsing, "telegram_api_call", api)
    assert browsing.send_browse_page(db_session, "latest", 123, "secret", NOW)
    assert [call.args[0] for call in api.call_args_list] == ["sendMessage", "editMessageReplyMarkup"]


def test_callback_refresh_and_failed_edit(db_session, monkeypatch):
    seed(db_session)
    query = dict(id="callback", message=dict(chat=dict(id=123), message_id=456),
                 data=browsing.button_data("latest", "r", STAMP, 123, 456, "secret"))
    api = Mock(return_value=True)
    monkeypatch.setattr(browsing, "telegram_api_call", api)
    assert browsing.handle_browse_callback(db_session, query, "secret", NOW + timedelta(minutes=1))
    assert api.call_args.args[0] == "editMessageText"
    new_data = api.call_args.args[1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert browsing.read_button(new_data, 123, 456, "secret", STAMP + 60)[2] == STAMP + 60
    api.reset_mock(side_effect=True)
    api.side_effect = [True, None, True]
    assert not browsing.handle_browse_callback(db_session, query, "secret", NOW)
    assert "Could not update" in api.call_args.args[1]["text"]


def test_invalid_callback_never_queries_database(monkeypatch):
    api = Mock()
    monkeypatch.setattr(browsing, "telegram_api_call", api)
    assert not browsing.handle_browse_callback(None, dict(id="callback", data="tampered"), "secret", NOW)
    assert api.call_args.args[0] == "answerCallbackQuery"


def test_repeated_edit_is_success(monkeypatch):
    monkeypatch.setattr(notifications, "settings", type("Config", (), {"telegram_bot_token": "fake"})())
    monkeypatch.setattr(notifications.requests, "post", Mock(return_value=Mock(ok=False,
        json=lambda: {"ok": False, "description": "Bad Request: message is not modified"})))
    assert notifications.telegram_api_call("editMessageText", {}) is True


def test_webhook_routes_callbacks_without_subscription_changes(db_session, monkeypatch):
    from types import SimpleNamespace
    from app.api import routes
    from app import crud
    crud.activate_telegram_subscriber(db_session, "123")
    crud.deactivate_telegram_subscriber(db_session, "123")
    db_session.commit()
    monkeypatch.setattr(routes, "settings", SimpleNamespace(telegram_webhook_secret="secret"))
    handler = Mock(return_value=True)
    monkeypatch.setattr(routes, "handle_browse_callback", handler)
    routes.telegram_webhook({"callback_query": {"id": "cb", "data": "test"}}, db_session, "secret")
    handler.assert_called_once()
    assert crud.telegram_subscription_state(db_session, "123") is False


def test_browsing_command_does_not_reactivate_stopped_chat(db_session, monkeypatch):
    from types import SimpleNamespace
    from app.api import routes
    from app import crud
    crud.activate_telegram_subscriber(db_session, "123")
    crud.deactivate_telegram_subscriber(db_session, "123")
    db_session.commit()
    monkeypatch.setattr(routes, "settings", SimpleNamespace(telegram_webhook_secret="secret"))
    send = Mock(return_value=True)
    monkeypatch.setattr(routes, "send_browse_page", send)
    routes.telegram_webhook({"message": {"chat": {"id": 123}, "text": "/latest"}}, db_session, "secret")
    assert send.call_args.args[1:3] == ("latest", "123")
    assert crud.telegram_subscription_state(db_session, "123") is False
