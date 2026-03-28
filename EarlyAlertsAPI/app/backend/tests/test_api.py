"""FastAPI TestClient smoke tests – all 5 endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Create a TestClient with a temporary SQLite database."""
    import os
    tmp = tmp_path_factory.mktemp("db")
    os.environ["EARLY_ALERTS_STORAGE__SQLITE_PATH"] = str(tmp / "test_alerts.db")
    os.environ["EARLY_ALERTS_STORAGE__DUCKDB_PATH"] = str(tmp / "test_warehouse.duckdb")

    # Clear lru_cache so the env override takes effect
    from app.backend.core.config import get_settings
    get_settings.cache_clear()

    from app.backend.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c

    # Restore
    get_settings.cache_clear()
    os.environ.pop("EARLY_ALERTS_STORAGE__SQLITE_PATH", None)
    os.environ.pop("EARLY_ALERTS_STORAGE__DUCKDB_PATH", None)


def test_health_returns_200(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "city" in body
    assert "open_events" in body


def test_config_returns_200(client):
    response = client.get("/api/v1/config")
    assert response.status_code == 200
    body = response.json()
    assert body["city"] == "monterrey"
    assert "provider" in body


def test_alerts_latest_returns_200(client):
    response = client.get("/api/v1/alerts/latest")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_events_open_returns_200(client):
    response = client.get("/api/v1/events/open")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_run_once_returns_202(client, monkeypatch):
    """POST /jobs/run-once returns 202 (uses a fake provider to avoid network calls)."""
    from app.backend.tests.conftest import FakeProvider

    fake = FakeProvider(precip_mm=0.0)

    # The import happens inside the function body of jobs.py so patch at the source
    monkeypatch.setattr(
        "app.backend.ingestion.open_meteo.OpenMeteoProvider",
        lambda **kwargs: fake,
    )

    response = client.post("/api/v1/jobs/run-once")
    assert response.status_code == 202
    body = response.json()
    assert "run_id" in body
    assert body["status"] == "ok"
