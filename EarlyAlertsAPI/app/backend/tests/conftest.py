"""Shared fixtures for the full test suite."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generator

import pytest
import yaml

from app.backend.core.config import get_settings
from app.backend.core.rule_pack import load_rule_pack
from app.backend.core.zone_catalog import load_zone_catalog
from app.backend.ingestion.provider_base import ForecastProvider
from app.backend.state.database import init_db, get_session
from app.backend.state.tables import metadata


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_hourly_block(precip_value: float, hours: int = 6) -> dict:
    """Return a minimal Open-Meteo-shaped hourly block."""
    times = [f"2026-01-15T{h:02d}:00" for h in range(hours)]
    return {
        "hourly": {
            "time": times,
            "precipitation": [precip_value] * hours,
        }
    }


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def rule_pack(settings):
    return load_rule_pack(str(settings.rule_pack_path))


@pytest.fixture(scope="session")
def zone_catalog(settings):
    return load_zone_catalog(str(settings.zone_catalog_path))


@pytest.fixture(scope="session")
def baseline_table(settings):
    with open(settings.baseline_ratios_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture()
def in_memory_db():
    """Fresh in-memory SQLite; tables created, session available."""
    import sqlalchemy as sa
    engine = sa.create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)

    # Patch the module-level engine so get_session() works for this test
    import app.backend.state.database as db_mod
    old_engine = db_mod._engine
    db_mod._engine = engine
    yield engine
    db_mod._engine = old_engine
    engine.dispose()


class FakeProvider(ForecastProvider):
    """Returns canned precipitation per zone (all zones same value by default)."""

    def __init__(self, precip_mm: float = 0.0, zone_precip: dict[str, float] | None = None):
        self._default = precip_mm
        self._zone_precip = zone_precip or {}

    async def fetch_hourly_forecast(
        self, coordinates: list[tuple[float, float]], hours_ahead: int = 6
    ) -> list[dict]:
        return [_make_hourly_block(self._default, hours_ahead) for _ in coordinates]


class FakeProviderFailing(ForecastProvider):
    async def fetch_hourly_forecast(self, coordinates, hours_ahead=6):
        raise RuntimeError("Provider unavailable")


@pytest.fixture()
def fake_provider():
    return FakeProvider(precip_mm=0.0)


@pytest.fixture()
def rainy_provider():
    """Simulates heavy rain in sensitive zone hours."""
    return FakeProvider(precip_mm=3.0)


@pytest.fixture()
def failing_provider():
    return FakeProviderFailing()
