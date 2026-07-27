import pytest
from fastapi import HTTPException

from app.api.routes import _require_run_check_authorization


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
