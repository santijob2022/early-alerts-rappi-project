"""Open-Meteo forecast provider.

Uses a single HTTP call with comma-separated latitude/longitude parameters
(Open-Meteo batch API) to fetch all 14 centroids in one request.
Falls back to bounded parallel requests (asyncio.Semaphore) if batch fails.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.backend.ingestion.provider_base import ForecastProvider

logger = logging.getLogger(__name__)

_BATCH_FALLBACK_CONCURRENCY = 4
_HOURLY_VARIABLES = ["precipitation"]


class OpenMeteoProvider(ForecastProvider):
    def __init__(
        self,
        base_url: str = "https://api.open-meteo.com/v1/forecast",
        timeout_seconds: int = 30,
        max_retries: int = 2,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout_seconds
        self._max_retries = max_retries

    async def fetch_hourly_forecast(
        self,
        coordinates: list[tuple[float, float]],
        hours_ahead: int = 6,
    ) -> list[dict]:
        """Single HTTP call for all coordinates; falls back to concurrent if needed."""
        try:
            return await self._batch_fetch(coordinates, hours_ahead)
        except httpx.HTTPError as exc:
            logger.warning("Batch fetch failed (%s), falling back to individual calls", exc)
            return await self._individual_fetch(coordinates, hours_ahead)

    async def _batch_fetch(
        self, coordinates: list[tuple[float, float]], hours_ahead: int
    ) -> list[dict]:
        lats = ",".join(str(lat) for lat, _ in coordinates)
        lons = ",".join(str(lon) for _, lon in coordinates)
        params = {
            "latitude": lats,
            "longitude": lons,
            "hourly": ",".join(_HOURLY_VARIABLES),
            "forecast_hours": hours_ahead,
            "timezone": "UTC",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await self._request_with_retry(client, params)
        data: Any = response.json()
        # Open-Meteo returns a list when multiple coords are given
        if isinstance(data, list):
            return data
        # Single-element response wrapped in a dict
        return [data]

    async def _individual_fetch(
        self, coordinates: list[tuple[float, float]], hours_ahead: int
    ) -> list[dict]:
        sem = asyncio.Semaphore(_BATCH_FALLBACK_CONCURRENCY)

        async def _fetch_one(lat: float, lon: float) -> dict:
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(_HOURLY_VARIABLES),
                "forecast_hours": hours_ahead,
                "timezone": "UTC",
            }
            async with sem, httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await self._request_with_retry(client, params)
            return resp.json()  # type: ignore[return-value]

        tasks = [_fetch_one(lat, lon) for lat, lon in coordinates]
        return list(await asyncio.gather(*tasks))

    async def _request_with_retry(
        self, client: httpx.AsyncClient, params: dict
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await client.get(self._base_url, params=params)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                logger.warning("HTTP %s on attempt %d/%d", exc.response.status_code, attempt + 1, self._max_retries + 1)
            except httpx.TransportError as exc:
                last_exc = exc
                logger.warning("Transport error on attempt %d: %s", attempt + 1, exc)
            if attempt < self._max_retries:
                await asyncio.sleep(1.0)
        raise last_exc  # type: ignore[misc]
