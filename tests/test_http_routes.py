from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.database import get_db
from app.services.event_detector import DetectionResult
from app.services.job_lock import CheckAlreadyRunning


@pytest.fixture
def client(monkeypatch):
    # Mount only routes so HTTP tests cannot migrate or connect to a configured database.
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: None
    monkeypatch.setattr(routes, "settings", SimpleNamespace(run_check_secret="test-secret"))
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("method,path", [("post", "/run-check"), ("post", "/run-reminders"), ("get", "/sources/status")])
def test_operational_endpoints_require_auth(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_reminders_route_does_not_scrape(client, monkeypatch):
    reminders, scrape = Mock(return_value=3), Mock()
    monkeypatch.setattr(routes, "run_sale_reminder_check", reminders)
    monkeypatch.setattr(routes, "run_event_check", scrape)
    response = client.post("/run-reminders", headers={"Authorization": "Bearer test-secret"})
    assert response.json() == {"notifications_sent": 3}
    scrape.assert_not_called()


def test_all_sources_failed_returns_502(client, monkeypatch):
    result = DetectionResult(source_results=[dict(name="Ticketmaster Singapore", status="failed", events=0, seeded=False, error="SourceFetchError", warnings=[])])
    monkeypatch.setattr(routes, "run_event_check", Mock(return_value=result))
    response = client.post("/run-check", headers={"Authorization": "Bearer test-secret"})
    assert response.status_code == 502
    assert response.json()["sources"][0]["status"] == "failed"


def test_concurrent_check_returns_conflict(client, monkeypatch):
    monkeypatch.setattr(routes, "run_event_check", Mock(side_effect=CheckAlreadyRunning("Already running")))
    assert client.post("/run-check", headers={"Authorization": "Bearer test-secret"}).status_code == 409
