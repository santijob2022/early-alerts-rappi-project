"""Unit tests for app/agent/orchestrator.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.orchestrator import AlertOrchestrator


def _make_orchestrator(llm_response: str = "generated text") -> AlertOrchestrator:
    context_svc = MagicMock()
    context_svc.get_motor_context.return_value = "motor context"
    llm_client = MagicMock()
    llm_client.generate = AsyncMock(return_value=llm_response)
    return AlertOrchestrator(context_svc, llm_client, "system prompt")


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


class TestAlertOrchestrator:
    async def test_process_alert_returns_llm_text(self):
        orch = _make_orchestrator("mensaje generado")
        result = await orch.process_alert(BASE_ALERT)
        assert result == "mensaje generado"

    async def test_process_alert_calls_llm_generate(self):
        orch = _make_orchestrator()
        await orch.process_alert(BASE_ALERT)
        orch._llm.generate.assert_awaited_once()

    async def test_process_alert_passes_system_prompt(self):
        orch = _make_orchestrator()
        await orch.process_alert(BASE_ALERT)
        call_args = orch._llm.generate.call_args
        assert call_args[0][0] == "system prompt"

    async def test_process_alert_user_message_contains_zone(self):
        orch = _make_orchestrator()
        await orch.process_alert(BASE_ALERT)
        user_msg = orch._llm.generate.call_args[0][1]
        assert "Santiago" in user_msg

    async def test_process_alert_maps_alto_risk(self):
        orch = _make_orchestrator()
        await orch.process_alert({**BASE_ALERT, "risk_level": "alto"})
        user_msg = orch._llm.generate.call_args[0][1]
        assert "ALTO" in user_msg

    async def test_process_alert_maps_critico_risk(self):
        orch = _make_orchestrator()
        await orch.process_alert({**BASE_ALERT, "risk_level": "critico"})
        user_msg = orch._llm.generate.call_args[0][1]
        assert "CRÍTICO" in user_msg

    async def test_process_alert_maps_medio_risk(self):
        orch = _make_orchestrator()
        await orch.process_alert({**BASE_ALERT, "risk_level": "medio"})
        user_msg = orch._llm.generate.call_args[0][1]
        assert "MEDIO" in user_msg

    async def test_process_alert_propagates_llm_runtime_error(self):
        context_svc = MagicMock()
        llm_client = MagicMock()
        llm_client.generate = AsyncMock(side_effect=RuntimeError("LLM generation failed: timeout"))
        orch = AlertOrchestrator(context_svc, llm_client, "system prompt")

        with pytest.raises(RuntimeError, match="LLM generation failed"):
            await orch.process_alert(BASE_ALERT)

    async def test_process_alert_unknown_risk_upcased(self):
        orch = _make_orchestrator()
        await orch.process_alert({**BASE_ALERT, "risk_level": "unknown_level"})
        user_msg = orch._llm.generate.call_args[0][1]
        assert "UNKNOWN_LEVEL" in user_msg

    async def test_process_alert_empty_risk_level(self):
        """Empty risk_level should not crash — should produce empty string label."""
        orch = _make_orchestrator()
        result = await orch.process_alert({**BASE_ALERT, "risk_level": ""})
        assert isinstance(result, str)
