"""Tests for the pure decision engine – mandatory scenarios from PLAN.md §5.1"""
from __future__ import annotations

import pytest

from app.backend.core.constants import DecisionType, RiskLevel
from app.backend.core.models import DecisionInput
from app.backend.decision.engine import evaluate_zone
from app.backend.decision.earnings import recommend_earnings
from app.backend.decision.projections import bucketize_rain, project_ratio
from app.backend.decision.severity import classify_risk


# ── Scenario 1: Santiago, peak, 1.2 mm/hr, sensitive zone ──────────────────
def test_s1_santiago_peak_sensitive_triggers_alert(rule_pack, baseline_table, zone_catalog):
    """Santiago + peak + 1.2 mm/hr (above sensitive threshold 1.0) → ALERT, risk ≥ ALTO, ratio ≥ 2.70."""
    inp = DecisionInput(zone="Santiago", forecast_hour=13, forecast_precip_mm=1.2,
                        current_hour=12, current_earnings_mxn=70.0)
    out = evaluate_zone(inp, rule_pack, baseline_table, None, {}, zone_catalog)

    assert out.decision_type == DecisionType.ALERT
    assert out.risk_level in (RiskLevel.ALTO, RiskLevel.CRITICO)
    assert out.projected_ratio is not None and out.projected_ratio >= 2.700
    assert out.recommended_earnings_mxn == 80.0


# ── Scenario 2: Centro, peak, 1.2 mm/hr, NOT sensitive → WATCH ─────────────
def test_s2_centro_below_base_trigger_is_watch(rule_pack, baseline_table, zone_catalog):
    """Centro is not sensitive; 1.2 mm/hr < 2.0 base trigger → WATCH."""
    inp = DecisionInput(zone="Centro", forecast_hour=13, forecast_precip_mm=1.2,
                        current_hour=12, current_earnings_mxn=70.0)
    out = evaluate_zone(inp, rule_pack, baseline_table, None, {}, zone_catalog)

    assert out.decision_type == DecisionType.WATCH


# ── Scenario 3: Centro, peak, 2.5 mm/hr → ALERT, ALTO ─────────────────────
def test_s3_centro_moderate_rain_peak_alto(rule_pack, baseline_table, zone_catalog):
    """Centro, hour 14, 2.5 mm/hr ≥ 2.0 → ALERT, risk ALTO."""
    inp = DecisionInput(zone="Centro", forecast_hour=14, forecast_precip_mm=2.5,
                        current_hour=13, current_earnings_mxn=72.0)
    out = evaluate_zone(inp, rule_pack, baseline_table, None, {}, zone_catalog)

    assert out.decision_type == DecisionType.ALERT
    assert out.risk_level == RiskLevel.ALTO


# ── Scenario 4: t+3 horizon → WATCH (no outbox) ────────────────────────────
def test_s4_watchlist_horizon_t3_is_watch(rule_pack, baseline_table, zone_catalog):
    """Forecast 3h ahead (lead 180 min) → WATCH regardless of precip."""
    inp = DecisionInput(zone="Centro", forecast_hour=16, forecast_precip_mm=3.0,
                        current_hour=13, current_earnings_mxn=55.6)
    out = evaluate_zone(inp, rule_pack, baseline_table, None, {}, zone_catalog)

    assert out.decision_type == DecisionType.WATCH
    assert out.lead_time_min == 180


# ── Bucketize rain ──────────────────────────────────────────────────────────
def test_bucketize_dry(rule_pack):
    from app.backend.core.constants import RainBucket
    assert bucketize_rain(0.05, rule_pack) == RainBucket.DRY


def test_bucketize_light(rule_pack):
    from app.backend.core.constants import RainBucket
    assert bucketize_rain(1.0, rule_pack) == RainBucket.LIGHT


def test_bucketize_moderate(rule_pack):
    from app.backend.core.constants import RainBucket
    assert bucketize_rain(2.5, rule_pack) == RainBucket.MODERATE


def test_bucketize_heavy(rule_pack):
    from app.backend.core.constants import RainBucket
    assert bucketize_rain(7.0, rule_pack) == RainBucket.HEAVY


# ── Severity classification ─────────────────────────────────────────────────
def test_severity_none_below_floor(rule_pack):
    assert classify_risk(1.30, 1.0, rule_pack) is None


def test_severity_medio(rule_pack):
    assert classify_risk(1.60, 1.0, rule_pack) == RiskLevel.MEDIO


def test_severity_alto(rule_pack):
    assert classify_risk(1.90, 2.0, rule_pack) == RiskLevel.ALTO


def test_severity_critico(rule_pack):
    assert classify_risk(2.30, 2.0, rule_pack) == RiskLevel.CRITICO


def test_severity_heavy_rain_override(rule_pack):
    """Precip ≥ 5 mm + ALTO → force CRITICO."""
    assert classify_risk(1.85, 6.0, rule_pack) == RiskLevel.CRITICO


# ── Earnings recommendation ─────────────────────────────────────────────────
def test_earnings_below_target(rule_pack):
    rec, uplift = recommend_earnings(55.6, rule_pack)
    assert rec == 80.0
    assert round(uplift, 2) == 24.4


def test_earnings_above_target(rule_pack):
    rec, uplift = recommend_earnings(90.0, rule_pack)
    assert rec == 90.0
    assert uplift == 0.0
