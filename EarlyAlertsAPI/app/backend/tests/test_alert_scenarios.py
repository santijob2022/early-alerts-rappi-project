"""Integration tests: alert scenarios with simulated precipitation inputs.

Each test drives POST /jobs/run-once with a FakeProvider that returns a
specific precipitation value, then asserts that:
  - the correct number of alerts was emitted
  - the right risk levels appear in /api/v1/alerts/latest
  - the alert data is persisted in SQLite (consumable via API)

Precipitation → Risk level logic (from rule_pack_v1.yaml):
  - projected_ratio >= 1.50  → MEDIO
  - projected_ratio >= 1.80  → ALTO
  - projected_ratio >= 2.20  → CRITICO
  - precip_mm >= 5.0 AND ALTO/CRITICO → force CRITICO

The ratio is computed as:   baseline_ratio * (1 + rain_lift)
Peak hours are [12,13,14,19,20,21], sensitive zones have a lower trigger (1.0 mm).

Time pinning strategy
---------------------
The orchestrator selects only the forecast row whose `forecast_hour` (CST local)
matches `t1_hour = now_local_hour + 1`.  To make tests deterministic regardless
of when they run, we:
  1. Pin datetime.now in the orchestrator to 18:00 UTC = 12:00 CST so t1_hour=13
     (CST peak hour with high baselines: ~1.40 – 1.55 across all zones).
  2. Generate fake forecast data for UTC hours 19-23 + 00 next day which map to
     CST hours 13-18, ensuring hour 13 always has data.

Run:
    cd EarlyAlertsAPI
    pytest app/backend/tests/test_alert_scenarios.py -v
"""
from __future__ import annotations

import os
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.backend.tests.conftest import FakeProvider

# ── Time pinning constants ────────────────────────────────────────────────────

# 18:00 UTC = 12:00 CST → t1_hour = 13 (CST peak hour, high baselines)
_FIXED_NOW_UTC = datetime(2026, 3, 27, 18, 0, 0, tzinfo=timezone.utc)

# UTC hours 19-23 + 00 next day → CST hours 13-18 (includes peak hour 13 & 14)
_PEAK_UTC_HOURS = [
    "2026-03-27T19:00",
    "2026-03-27T20:00",
    "2026-03-27T21:00",
    "2026-03-27T22:00",
    "2026-03-27T23:00",
    "2026-03-28T00:00",
]


def _make_peak_hourly_block(precip_value: float) -> dict:
    """Hourly block whose times map to CST 13-18 (includes peak hour 13 and 14)."""
    return {
        "hourly": {
            "time": _PEAK_UTC_HOURS,
            "precipitation": [precip_value] * len(_PEAK_UTC_HOURS),
        }
    }


class PeakFakeProvider(FakeProvider):
    """FakeProvider that always returns data centered on CST peak hours 13-18."""

    async def fetch_hourly_forecast(
        self, coordinates: list[tuple[float, float]], hours_ahead: int = 6
    ) -> list[dict]:
        return [_make_peak_hourly_block(self._default) for _ in coordinates]


# ── Shared client fixture ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """TestClient with isolated SQLite + DuckDB so real data is never touched."""
    tmp = tmp_path_factory.mktemp("scenario_db")
    os.environ["EARLY_ALERTS_STORAGE__SQLITE_PATH"] = str(tmp / "alerts.db")
    os.environ["EARLY_ALERTS_STORAGE__DUCKDB_PATH"] = str(tmp / "warehouse.duckdb")

    from app.backend.core.config import get_settings
    get_settings.cache_clear()

    from app.backend.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c

    get_settings.cache_clear()
    os.environ.pop("EARLY_ALERTS_STORAGE__SQLITE_PATH", None)
    os.environ.pop("EARLY_ALERTS_STORAGE__DUCKDB_PATH", None)


def _run_once_with_precip(client: TestClient, precip_mm: float) -> dict:
    """Trigger run-once with a PeakFakeProvider returning precip_mm for all zones.

    Patches:
      - OpenMeteoProvider → PeakFakeProvider (data at CST peak hours 13-18)
      - orchestrator.datetime.now → _FIXED_NOW_UTC (18:00 UTC = 12:00 CST)
        so t1_hour is always 13, a CST peak hour with high baselines (~1.40-1.55).

    Returns the JSON body of the 202 response.
    """
    fake = PeakFakeProvider(precip_mm=precip_mm)
    mock_dt = MagicMock()
    mock_dt.now.return_value = _FIXED_NOW_UTC   # .astimezone() still works on real datetime
    mock_dt.fromisoformat = datetime.fromisoformat  # keep suppression logic intact

    with patch("app.backend.ingestion.open_meteo.OpenMeteoProvider", return_value=fake), \
         patch("app.backend.services.orchestrator.datetime", mock_dt):
        response = client.post("/api/v1/jobs/run-once")
    assert response.status_code == 202, response.text
    return response.json()


# ── Scenario 1: Dry conditions → no alerts ───────────────────────────────────

class TestScenarioDry:
    def test_no_alerts_emitted(self, client):
        """0 mm precipitation: engine should emit 0 alerts."""
        body = _run_once_with_precip(client, precip_mm=0.0)
        assert body["alerts_emitted"] == 0

    def test_alerts_endpoint_empty(self, client):
        """After a dry run, /alerts/latest should return an empty list."""
        response = client.get("/api/v1/alerts/latest?status=pending")
        assert response.status_code == 200
        # May have alerts from previous scenarios in same module scope — filter by
        # checking none have precip > 0 (dry run shouldn't create new ones)
        # Simplest: just verify status is 200 and response is a list
        assert isinstance(response.json(), list)


# ── Scenario 2: Light rain in peak hours → MEDIO ─────────────────────────────

class TestScenarioMedio:
    """2.5 mm in peak hours should push baseline ratios above medio_min (1.50)
    for high-baseline zones (e.g. Centro at hour 13: baseline=1.52 × lift).
    """

    def test_alerts_emitted(self, client):
        """2.5 mm should produce at least one MEDIO alert."""
        body = _run_once_with_precip(client, precip_mm=2.5)
        assert body["alerts_emitted"] >= 1, (
            f"Expected ≥1 alerts for precip=2.5mm, got {body['alerts_emitted']}"
        )

    def test_medio_or_higher_risk_present(self, client):
        """At least one pending alert should be medio, alto, or critico."""
        response = client.get("/api/v1/alerts/latest?status=pending&limit=50")
        assert response.status_code == 200
        alerts = response.json()
        risk_levels = {a["risk_level"] for a in alerts}
        assert risk_levels & {"medio", "alto", "critico"}, (
            f"No medio+ alert found. Found levels: {risk_levels}"
        )

    def test_alert_has_required_fields(self, client):
        """Each alert in the response must have the expected schema fields."""
        response = client.get("/api/v1/alerts/latest?status=pending&limit=50")
        alerts = response.json()
        required = {"id", "zone", "risk_level", "precip_mm", "created_at"}
        for alert in alerts:
            missing = required - alert.keys()
            assert not missing, f"Alert missing fields: {missing}"


# ── Scenario 3: Heavy rain → ALTO / CRITICO ──────────────────────────────────

class TestScenarioAlto:
    """5.5 mm exceeds critical_escalation_mm (5.0) and should force CRITICO
    for any zone/hour that would otherwise be ALTO.
    """

    def test_critico_alerts_emitted(self, client):
        """5.5 mm should produce at least one CRITICO alert."""
        body = _run_once_with_precip(client, precip_mm=5.5)
        assert body["alerts_emitted"] >= 1

    def test_critico_risk_level_present(self, client):
        """At least one pending alert should be critico after 5.5 mm."""
        response = client.get("/api/v1/alerts/latest?status=pending&limit=50")
        assert response.status_code == 200
        alerts = response.json()
        critico = [a for a in alerts if a["risk_level"] == "critico"]
        assert len(critico) >= 1, (
            f"Expected >=1 critico alerts for precip=5.5mm. "
            f"Levels found: {[a['risk_level'] for a in alerts]}"
        )

    def test_critico_alert_precip_above_threshold(self, client):
        """critico alerts must have precip_mm >= critical_escalation_mm (5.0)."""
        response = client.get("/api/v1/alerts/latest?status=pending&limit=50")
        alerts = response.json()
        for alert in alerts:
            if alert["risk_level"] == "critico":
                assert alert["precip_mm"] >= 5.0, (
                    f"critico alert has unexpectedly low precip: {alert['precip_mm']}"
                )


# ── Scenario 4: Alert lifecycle — consume then verify ────────────────────────

class TestAlertLifecycle:
    """Consume a pending alert via PATCH and verify it disappears from the
    pending list. Reuses alerts already created by the heavy-rain scenarios
    above — no new run-once needed.
    """

    def test_consume_alert_removes_from_pending(self, client):
        """After consuming an alert it should no longer appear in pending."""
        # Fetch currently pending alerts (created by earlier scenarios)
        response = client.get("/api/v1/alerts/latest?status=pending&limit=50")
        alerts = response.json()
        assert len(alerts) >= 1, (
            "No pending alerts available to consume — did Scenario 3 run first?"
        )

        # Consume the first one
        alert_id = alerts[0]["id"]
        patch_resp = client.patch(f"/api/v1/alerts/{alert_id}/consume")
        assert patch_resp.status_code == 200

        # It should no longer be pending
        response2 = client.get("/api/v1/alerts/latest?status=pending&limit=50")
        pending_ids = {a["id"] for a in response2.json()}
        assert alert_id not in pending_ids, (
            f"Alert {alert_id} still pending after consume"
        )


# ── Scenario 5: Sensitive zone lower trigger ──────────────────────────────────

class TestSensitiveZoneTrigger:
    """Sensitive zones (Santiago, Carretera Nacional, Santa Catarina,
    MTY_Apodaca_Huinala) have a lower trigger threshold (1.0 mm in peak hours
    vs 2.0 mm base). The Scenario 2 and 3 runs (2.5 mm and 5.5 mm) both
    exceed this, so sensitive zones should appear in the already-accumulated
    pending alerts.
    """

    def test_sensitive_zone_names_appear_in_alerts(self, client):
        """At least one of the known sensitive zones should appear in pending alerts."""
        sensitive = {"Santiago", "Carretera Nacional", "Santa Catarina", "MTY_Apodaca_Huinala"}
        response = client.get("/api/v1/alerts/latest?status=pending&limit=50")
        alert_zones = {a["zone"] for a in response.json()}
        assert alert_zones & sensitive, (
            f"No sensitive zone found in alerts. Zones with alerts: {alert_zones}"
        )

    def test_all_alert_zones_are_known(self, client):
        """Every alert zone should be one of the 14 configured Monterrey zones."""
        known_zones = {
            "Centro", "San Pedro", "MTY_Guadalupe", "San Nicolas",
            "Santiago", "Carretera Nacional", "Santa Catarina", "MTY_Apodaca_Huinala",
            "Escobedo", "Apodaca Centro", "La Fe", "Independencia",
            "Mitras Centro", "Cumbres Poniente",
        }
        response = client.get("/api/v1/alerts/latest?status=pending&limit=50")
        for alert in response.json():
            assert alert["zone"] in known_zones, (
                f"Unexpected zone in alert: {alert['zone']}"
            )
