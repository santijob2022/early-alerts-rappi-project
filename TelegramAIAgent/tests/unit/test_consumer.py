"""Unit tests for app/services/alerts_api/consumer.py."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.services.alerts_api.consumer import AlertsAPIConsumer

BASE_URL = "http://localhost:8000"


@pytest.fixture()
def consumer():
    return AlertsAPIConsumer(BASE_URL)


class TestFetchPendingAlerts:
    @respx.mock
    async def test_returns_list_of_alerts(self, consumer):
        alerts = [{"id": "a1", "zone": "Santiago"}, {"id": "a2", "zone": "Cumbres"}]
        respx.get(f"{BASE_URL}/api/v1/alerts/latest").mock(
            return_value=httpx.Response(200, json=alerts)
        )
        result = await consumer.fetch_pending_alerts()
        assert result == alerts

    @respx.mock
    async def test_returns_empty_list_when_none_pending(self, consumer):
        respx.get(f"{BASE_URL}/api/v1/alerts/latest").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await consumer.fetch_pending_alerts()
        assert result == []

    @respx.mock
    async def test_raises_on_http_error(self, consumer):
        respx.get(f"{BASE_URL}/api/v1/alerts/latest").mock(
            return_value=httpx.Response(500, text="error")
        )
        with pytest.raises(httpx.HTTPStatusError):
            await consumer.fetch_pending_alerts()

    @respx.mock
    async def test_sends_pending_status_param(self, consumer):
        route = respx.get(f"{BASE_URL}/api/v1/alerts/latest").mock(
            return_value=httpx.Response(200, json=[])
        )
        await consumer.fetch_pending_alerts()
        request = route.calls.last.request
        assert "status=pending" in str(request.url)


class TestMarkConsumed:
    @respx.mock
    async def test_success_no_exception(self, consumer):
        respx.patch(f"{BASE_URL}/api/v1/alerts/a-001/consume").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        # Should not raise
        await consumer.mark_consumed("a-001")

    @respx.mock
    async def test_404_is_silent(self, consumer):
        respx.patch(f"{BASE_URL}/api/v1/alerts/ghost/consume").mock(
            return_value=httpx.Response(404, json={"detail": "not found"})
        )
        # Should not raise
        await consumer.mark_consumed("ghost")

    @respx.mock
    async def test_500_raises(self, consumer):
        respx.patch(f"{BASE_URL}/api/v1/alerts/a-002/consume").mock(
            return_value=httpx.Response(500, text="server error")
        )
        with pytest.raises(httpx.HTTPStatusError):
            await consumer.mark_consumed("a-002")


class TestTriggerRunOnce:
    @respx.mock
    async def test_returns_response_dict(self, consumer):
        payload = {"alerts_emitted": 2, "status": "ok"}
        respx.post(f"{BASE_URL}/api/v1/jobs/run-once").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await consumer.trigger_run_once()
        assert result == payload

    @respx.mock
    async def test_raises_on_http_error(self, consumer):
        respx.post(f"{BASE_URL}/api/v1/jobs/run-once").mock(
            return_value=httpx.Response(503, text="unavailable")
        )
        with pytest.raises(httpx.HTTPStatusError):
            await consumer.trigger_run_once()


class TestGetHealth:
    @respx.mock
    async def test_returns_health_dict(self, consumer):
        health = {"status": "ok", "last_run": "2026-03-27T14:00:00", "open_events": 1}
        respx.get(f"{BASE_URL}/api/v1/health").mock(
            return_value=httpx.Response(200, json=health)
        )
        result = await consumer.get_health()
        assert result["status"] == "ok"
        assert result["open_events"] == 1

    @respx.mock
    async def test_raises_on_http_error(self, consumer):
        respx.get(f"{BASE_URL}/api/v1/health").mock(
            return_value=httpx.Response(503, text="down")
        )
        with pytest.raises(httpx.HTTPStatusError):
            await consumer.get_health()


class TestBaseUrlNormalization:
    @respx.mock
    async def test_trailing_slash_stripped(self):
        """Consumer with trailing slash in URL should still build correct endpoint."""
        consumer = AlertsAPIConsumer("http://localhost:8000/")
        respx.get("http://localhost:8000/api/v1/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        result = await consumer.get_health()
        assert result["status"] == "ok"
