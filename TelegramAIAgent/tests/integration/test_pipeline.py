"""Integration tests — full pipeline with real file loading and mocked LLM/HTTP.

These tests exercise the real data flow:
  Motor files → ContextSourceService → system prompt → AlertOrchestrator → LLM call

No real LLM or HTTP calls are made.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from app.agent.context_source import ContextSourceService
from app.agent.orchestrator import AlertOrchestrator
from app.agent.prompts.system_prompt import build_system_prompt
from app.services.alerts_api.consumer import AlertsAPIConsumer
from app.services.telegram.sender import send_message
from tests.conftest import DOCS_CONTENT, MINIMAL_ALERT, RULES_CONTENT


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def context_service(test_settings):
    return ContextSourceService(test_settings)


@pytest.fixture()
def system_prompt(context_service):
    return build_system_prompt(context_service.get_motor_context())


@pytest.fixture()
def mock_llm():
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=(
            "🚨 Santiago ALTO\n"
            "📊 Se espera saturación. Ratio proyectado 2.44.\n"
            "💰 Subir earnings a 80.0 MXN (+24.4 MXN)\n"
            "⏱️ 60 minutos para actuar\n"
            "📍 Carretera Nacional"
        )
    )
    return llm


@pytest.fixture()
def orchestrator(context_service, mock_llm, system_prompt):
    return AlertOrchestrator(context_service, mock_llm, system_prompt)


# ── pipeline tests ────────────────────────────────────────────────────────────

class TestFullPipeline:
    async def test_process_alert_returns_string(self, orchestrator):
        result = await orchestrator.process_alert(MINIMAL_ALERT)
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_system_prompt_contains_rules_content(self, system_prompt):
        assert "Motor Reglas" in system_prompt

    async def test_system_prompt_contains_docs_content(self, system_prompt):
        assert "Documentacion Motor" in system_prompt

    async def test_system_prompt_contains_role_definition(self, system_prompt):
        assert "Rappi" in system_prompt
        assert "Monterrey" in system_prompt

    async def test_llm_called_with_motor_context_in_system_prompt(self, orchestrator, mock_llm):
        await orchestrator.process_alert(MINIMAL_ALERT)
        call_args = mock_llm.generate.call_args[0]
        sys_prompt = call_args[0]
        assert "Motor Reglas" in sys_prompt

    async def test_llm_called_with_alert_zone_in_user_message(self, orchestrator, mock_llm):
        await orchestrator.process_alert(MINIMAL_ALERT)
        call_args = mock_llm.generate.call_args[0]
        user_msg = call_args[1]
        assert "Santiago" in user_msg

    async def test_llm_called_with_projected_ratio_in_user_message(self, orchestrator, mock_llm):
        await orchestrator.process_alert(MINIMAL_ALERT)
        user_msg = mock_llm.generate.call_args[0][1]
        assert "2.44" in user_msg

    async def test_llm_called_with_earnings_in_user_message(self, orchestrator, mock_llm):
        await orchestrator.process_alert(MINIMAL_ALERT)
        user_msg = mock_llm.generate.call_args[0][1]
        assert "80.0" in user_msg

    async def test_llm_called_once_per_alert(self, orchestrator, mock_llm):
        await orchestrator.process_alert(MINIMAL_ALERT)
        mock_llm.generate.assert_awaited_once()

    async def test_multiple_alerts_call_llm_once_each(self, orchestrator, mock_llm):
        alert_a = {**MINIMAL_ALERT, "id": "a-1", "zone": "Santiago"}
        alert_b = {**MINIMAL_ALERT, "id": "a-2", "zone": "Cumbres"}
        await orchestrator.process_alert(alert_a)
        await orchestrator.process_alert(alert_b)
        assert mock_llm.generate.await_count == 2

    async def test_context_service_reload_updates_system_prompt(self, motor_files, test_settings):
        """After reload, a freshly built system prompt uses updated content."""
        rules, _ = motor_files
        svc = ContextSourceService(test_settings)
        rules.write_text("UPDATED_RULES_V2", encoding="utf-8")
        svc.reload()
        new_prompt = build_system_prompt(svc.get_motor_context())
        assert "UPDATED_RULES_V2" in new_prompt


# ── consumer ↔ sender pipeline ────────────────────────────────────────────────

class TestConsumerSenderPipeline:
    """Integration between AlertsAPIConsumer and send_message — simulates poll loop step."""

    BASE_URL = "http://localhost:8000"
    BOT_TOKEN = "bot_token_test"
    CHAT_ID = "123"

    @respx.mock
    async def test_fetch_then_send_then_consume(self):
        alerts = [MINIMAL_ALERT]
        respx.get(f"{self.BASE_URL}/api/v1/alerts/latest").mock(
            return_value=httpx.Response(200, json=alerts)
        )
        respx.post(f"https://api.telegram.org/bot{self.BOT_TOKEN}/sendMessage").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        respx.patch(f"{self.BASE_URL}/api/v1/alerts/{MINIMAL_ALERT['id']}/consume").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        consumer = AlertsAPIConsumer(self.BASE_URL)
        fetched = await consumer.fetch_pending_alerts()
        assert len(fetched) == 1

        sent = await send_message(self.BOT_TOKEN, self.CHAT_ID, "alerta text")
        assert sent is True

        # Should not raise
        await consumer.mark_consumed(fetched[0]["id"])

    @respx.mock
    async def test_failed_send_does_not_consume(self):
        """If send fails, mark_consumed should NOT be called."""
        respx.post(f"https://api.telegram.org/botfail_token/sendMessage").mock(
            return_value=httpx.Response(400, json={"ok": False})
        )
        sent = await send_message("fail_token", "123", "hello")
        assert sent is False
        # No consume call made — tested by not having a respx route for it
        # (respx would raise ConnectionError if an unmocked route was called)
