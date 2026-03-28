"""Normalizer: raw Open-Meteo response → ZoneForecastRow list.

Converts UTC timestamps to America/Monterrey local time and maps each
coordinate back to its zone name via an exact centroid match.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from zoneinfo import ZoneInfo

from app.backend.core.models import ZoneForecastRow
from app.backend.core.zone_catalog import ZoneCatalog

logger = logging.getLogger(__name__)

_LOCAL_TZ = ZoneInfo("America/Monterrey")


def _match_zone(
    lat: float,
    lon: float,
    catalog: ZoneCatalog,
    tol: float = 0.001,
) -> str | None:
    """Exact (within tolerance) centroid match."""
    for zone in catalog.zones:
        if abs(zone.latitude - lat) < tol and abs(zone.longitude - lon) < tol:
            return zone.name
    return None


def normalize(
    raw_responses: list[dict],
    coordinates: list[tuple[float, float]],
    catalog: ZoneCatalog,
    run_id: str,
    fetched_at: datetime,
) -> list[ZoneForecastRow]:
    """Convert raw Open-Meteo list into ZoneForecastRow entries.

    One entry per (zone × forecast_hour). Hours outside 0–23 are dropped.
    Precipitation is clamped to ≥ 0.
    """
    rows: list[ZoneForecastRow] = []

    for raw, (lat, lon) in zip(raw_responses, coordinates):
        zone = _match_zone(lat, lon, catalog)
        if zone is None:
            logger.warning("No zone match for coords (%.4f, %.4f) – skipping", lat, lon)
            continue

        hourly = raw.get("hourly", {})
        times: list[str] = hourly.get("time", [])
        precip_values: list[float | None] = hourly.get("precipitation", [])

        for time_str, precip in zip(times, precip_values):
            try:
                utc_dt = datetime.fromisoformat(time_str).replace(tzinfo=timezone.utc)
                local_dt = utc_dt.astimezone(_LOCAL_TZ)
            except ValueError:
                logger.warning("Could not parse time %r for zone %s", time_str, zone)
                continue

            local_hour = local_dt.hour
            if not 0 <= local_hour <= 23:
                continue

            # Open-Meteo occasionally returns null for precipitation
            safe_precip = max(float(precip or 0.0), 0.0)

            rows.append(
                ZoneForecastRow(
                    zone=zone,
                    forecast_hour=local_hour,
                    forecast_time=utc_dt,
                    precip_mm=safe_precip,
                    fetched_at=fetched_at,
                    run_id=run_id,
                )
            )

    return rows
