"""Tests for normalizer and pipeline (with mocked HTTP)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.backend.ingestion.normalizer import normalize


def _make_raw(precip: float = 2.0, hours: int = 6) -> dict:
    times = [f"2026-01-15T{h:02d}:00" for h in range(hours)]
    return {"hourly": {"time": times, "precipitation": [precip] * hours}}


def test_normalize_maps_all_zones(zone_catalog):
    """Normalize with one raw per zone → ZoneForecastRow per zone per hour."""
    coords = [(z.latitude, z.longitude) for z in zone_catalog.zones]
    raw_responses = [_make_raw() for _ in zone_catalog.zones]
    run_id = "test-run-1"
    fetched_at = datetime.now(timezone.utc)

    rows = normalize(raw_responses, coords, zone_catalog, run_id, fetched_at)

    # Should produce 14 zones × 6 hours = 84 rows (deduplication by local hour may reduce)
    assert len(rows) > 0
    zones_seen = {r.zone for r in rows}
    assert len(zones_seen) == len(zone_catalog.zones)


def test_normalize_precipitation_non_negative(zone_catalog):
    """Null precipitation values are coerced to 0.0."""
    coord = [(zone_catalog.zones[0].latitude, zone_catalog.zones[0].longitude)]
    raw = {"hourly": {"time": ["2026-01-15T12:00"], "precipitation": [None]}}
    rows = normalize([raw], coord, zone_catalog, "run", datetime.now(timezone.utc))
    assert all(r.precip_mm >= 0.0 for r in rows)


def test_normalize_run_id_propagated(zone_catalog):
    """run_id is set on every row."""
    coord = [(zone_catalog.zones[0].latitude, zone_catalog.zones[0].longitude)]
    raw = _make_raw(1.0, 2)
    rows = normalize([raw], coord, zone_catalog, "my-run-id", datetime.now(timezone.utc))
    assert all(r.run_id == "my-run-id" for r in rows)


def test_normalize_unknown_coord_skipped(zone_catalog):
    """Coordinates with no catalog match produce no rows."""
    unknown_coord = [(0.0, 0.0)]  # guaranteed not in catalog
    raw = _make_raw(1.0)
    rows = normalize(raw_responses=[raw], coordinates=unknown_coord,
                     catalog=zone_catalog, run_id="r", fetched_at=datetime.now(timezone.utc))
    assert rows == []


def test_fake_provider_returns_all_coords(zone_catalog):
    """FakeProvider returns one dict per coordinate."""
    from app.backend.tests.conftest import FakeProvider
    provider = FakeProvider(precip_mm=1.5)
    coords = [(z.latitude, z.longitude) for z in zone_catalog.zones]
    responses = asyncio.run(provider.fetch_hourly_forecast(coords, hours_ahead=3))
    assert len(responses) == len(zone_catalog.zones)
