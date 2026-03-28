"""HTTP client for EarlyAlertsAPI.

All communication with Module 2 goes through this class. Decoupled from agent
logic — the orchestrator never calls httpx directly.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(15.0)


class AlertsAPIConsumer:
    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    async def fetch_pending_alerts(self) -> list[dict]:
        """GET /api/v1/alerts/latest?status=pending"""
        url = f"{self._base}/api/v1/alerts/latest"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = client.build_request("GET", url, params={"status": "pending", "limit": 50})
            response = await client.send(resp)
            response.raise_for_status()
            return response.json()

    async def trigger_run_once(self) -> dict:
        """POST /api/v1/jobs/run-once — force an immediate engine cycle."""
        url = f"{self._base}/api/v1/jobs/run-once"
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(url)
            response.raise_for_status()
            return response.json()

    async def mark_consumed(self, alert_id: str) -> None:
        """PATCH /api/v1/alerts/{alert_id}/consume"""
        url = f"{self._base}/api/v1/alerts/{alert_id}/consume"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.patch(url)
            if response.status_code == 404:
                logger.warning("Alert %r not found when marking consumed — skipping", alert_id)
                return
            response.raise_for_status()

    async def get_health(self) -> dict:
        """GET /api/v1/health"""
        url = f"{self._base}/api/v1/health"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
