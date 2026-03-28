"""Unit tests for app/agent/prompts/system_prompt.py."""
from __future__ import annotations

import pytest

from app.agent.prompts.system_prompt import (
    build_system_prompt,
    build_user_message,
    map_risk_display,
)


# ── map_risk_display ──────────────────────────────────────────────────────────

class TestMapRiskDisplay:
    def test_medio(self):
        assert map_risk_display("medio") == "MEDIO"

    def test_alto(self):
        assert map_risk_display("alto") == "ALTO"

    def test_critico(self):
        assert map_risk_display("critico") == "CRÍTICO"

    def test_unknown_returns_uppercase(self):
        assert map_risk_display("custom") == "CUSTOM"

    def test_empty_string_returns_empty(self):
        assert map_risk_display("") == ""

    def test_case_insensitive_alto(self):
        assert map_risk_display("ALTO") == "ALTO"

    def test_case_insensitive_critico(self):
        assert map_risk_display("CRITICO") == "CRÍTICO"

    def test_mixed_case(self):
        assert map_risk_display("Medio") == "MEDIO"


# ── build_user_message ────────────────────────────────────────────────────────

class TestBuildUserMessage:
    BASE_ALERT = {
        "id": "a-1",
        "zone": "Santiago",
        "risk_level": "alto",
        "precip_mm": 4.2,
        "projected_ratio": 2.44,
        "recommended_earnings_mxn": 80.0,
        "uplift_mxn": 24.4,
        "lead_time_min": 60,
        "secondary_zones": ["Carretera Nacional"],
        "reason": "Precipitación 4.2 mm/hr >= trigger 2.0",
        "forecast_time": "2026-03-27T14:00:00",
    }

    def test_contains_zone(self):
        msg = build_user_message(self.BASE_ALERT, "ALTO")
        assert "Santiago" in msg

    def test_contains_risk_display(self):
        msg = build_user_message(self.BASE_ALERT, "ALTO")
        assert "ALTO" in msg

    def test_contains_precip(self):
        msg = build_user_message(self.BASE_ALERT, "ALTO")
        assert "4.2" in msg

    def test_projected_ratio_two_decimal_places(self):
        msg = build_user_message(self.BASE_ALERT, "ALTO")
        assert "2.44" in msg

    def test_recommended_earnings_one_decimal(self):
        msg = build_user_message(self.BASE_ALERT, "ALTO")
        assert "80.0" in msg

    def test_uplift_one_decimal(self):
        msg = build_user_message(self.BASE_ALERT, "ALTO")
        assert "24.4" in msg

    def test_lead_time(self):
        msg = build_user_message(self.BASE_ALERT, "ALTO")
        assert "60" in msg

    def test_secondary_zones_joined(self):
        msg = build_user_message(self.BASE_ALERT, "ALTO")
        assert "Carretera Nacional" in msg

    def test_secondary_zones_multiple_joined_with_comma(self):
        alert = {**self.BASE_ALERT, "secondary_zones": ["Zona A", "Zona B"]}
        msg = build_user_message(alert, "ALTO")
        assert "Zona A, Zona B" in msg

    def test_no_secondary_zones_shows_ninguna(self):
        alert = {**self.BASE_ALERT, "secondary_zones": []}
        msg = build_user_message(alert, "ALTO")
        assert "Ninguna" in msg

    def test_none_secondary_zones_shows_ninguna(self):
        alert = {**self.BASE_ALERT, "secondary_zones": None}
        msg = build_user_message(alert, "ALTO")
        assert "Ninguna" in msg

    def test_reason_included(self):
        msg = build_user_message(self.BASE_ALERT, "ALTO")
        assert "Precipitación 4.2 mm/hr >= trigger 2.0" in msg

    def test_forecast_time_included(self):
        msg = build_user_message(self.BASE_ALERT, "ALTO")
        assert "2026-03-27T14:00:00" in msg

    def test_missing_optional_fields_use_defaults(self):
        """Partial alert dict should not raise — falls back to zero/empty."""
        alert = {"zone": "Cumbres"}
        msg = build_user_message(alert, "BAJO")
        assert "Cumbres" in msg
        assert "BAJO" in msg

    def test_ratio_integer_value_still_two_decimals(self):
        alert = {**self.BASE_ALERT, "projected_ratio": 2}
        msg = build_user_message(alert, "ALTO")
        assert "2.00" in msg


# ── build_system_prompt ───────────────────────────────────────────────────────

class TestBuildSystemPrompt:
    def test_contains_motor_context(self):
        ctx = "MOTOR_CONTEXT_MARKER_XYZ"
        prompt = build_system_prompt(ctx)
        assert ctx in prompt

    def test_contains_role_definition(self):
        prompt = build_system_prompt("ctx")
        assert "Rappi" in prompt
        assert "Monterrey" in prompt

    def test_contains_section_rules(self):
        prompt = build_system_prompt("ctx")
        assert "5 secciones" in prompt

    def test_returns_string(self):
        assert isinstance(build_system_prompt("anything"), str)

    def test_empty_context_still_produces_prompt(self):
        prompt = build_system_prompt("")
        assert len(prompt) > 100
