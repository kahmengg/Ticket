import pytest
from types import SimpleNamespace
from unittest.mock import Mock
from fastapi import HTTPException

from app.api.routes import _require_run_check_authorization
from app.api import routes


@pytest.mark.parametrize("authorization", [None, "", "Basic test-secret", "Bearer wrong", "Bearer \u2603"])
def test_test_message_rejects_invalid_auth_without_side_effects(monkeypatch, authorization):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(run_check_secret="test-secret"))
    recipients = Mock()
    send = Mock()
    monkeypatch.setattr(routes, "get_notification_chat_ids", recipients)
    monkeypatch.setattr(routes, "send_telegram_message", send)
    with pytest.raises(HTTPException) as exc_info:
        routes.telegram_test_message(db=Mock(), authorization=authorization)
    assert exc_info.value.status_code == 401
    recipients.assert_not_called()
    send.assert_not_called()


def test_test_message_fails_closed_without_secret(monkeypatch):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(run_check_secret=None))
    send = Mock()
    monkeypatch.setattr(routes, "send_telegram_message", send)
    with pytest.raises(HTTPException) as exc_info:
        routes.telegram_test_message(db=Mock(), authorization="Bearer anything")
    assert exc_info.value.status_code == 503
    send.assert_not_called()


def test_authorized_test_message_returns_counts_only(monkeypatch):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(run_check_secret="test-secret"))
    monkeypatch.setattr(routes, "get_notification_chat_ids", Mock(return_value=["123", "456"]))
    send = Mock(return_value=2)
    monkeypatch.setattr(routes, "send_telegram_message", send)
    response = routes.telegram_test_message(db=Mock(), authorization="Bearer test-secret")
    assert response.model_dump() == {"configured_chat_count": 2, "sent": 2}
    assert send.call_args.kwargs["chat_ids"] == ["123", "456"]


@pytest.mark.parametrize("secret,provided,status", [
    (None, None, 503), (None, "anything", 503), ("", "", 503),
    ("secret", None, 403), ("secret", "wrong", 403), ("secret", "\u2603", 403),
])
def test_webhook_rejects_unauthenticated_updates(monkeypatch, secret, provided, status):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(telegram_webhook_secret=secret))
    db = Mock()
    upsert = Mock()
    send = Mock()
    monkeypatch.setattr(routes.crud, "upsert_telegram_subscriber", upsert)
    monkeypatch.setattr(routes, "send_telegram_message_to_chat", send)
    with pytest.raises(HTTPException) as exc_info:
        routes.telegram_webhook(
            update={"message": {"chat": {"id": 123}, "text": "/start"}},
            db=db, x_telegram_bot_api_secret_token=provided,
        )
    assert exc_info.value.status_code == status
    upsert.assert_not_called()
    db.commit.assert_not_called()
    send.assert_not_called()


def test_authenticated_webhook_still_processes_commands(monkeypatch, db_session):
    monkeypatch.setattr(routes, "settings", SimpleNamespace(telegram_webhook_secret="secret"))
    # Keep verification local: command replies must never reach real Telegram chats.
    send = Mock(return_value=True)
    monkeypatch.setattr(routes, "send_telegram_message_to_chat", send)
    response = routes.telegram_webhook(
        update={"message": {"chat": {"id": 123}, "text": "/start"}},
        db=db_session, x_telegram_bot_api_secret_token="secret",
    )
    assert response["saved"] is True
    assert routes.crud.list_active_telegram_chat_ids(db_session) == ["123"]
    send.assert_called_once()


def test_run_check_authorization_accepts_matching_bearer_token():
    _require_run_check_authorization("Bearer test-secret", "test-secret")


def test_run_check_authorization_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc_info:
        _require_run_check_authorization("Bearer wrong-secret", "test-secret")

    assert exc_info.value.status_code == 401
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_run_check_authorization_fails_closed_without_configured_secret():
    with pytest.raises(HTTPException) as exc_info:
        _require_run_check_authorization(None, None)

    assert exc_info.value.status_code == 503
