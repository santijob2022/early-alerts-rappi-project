"""AlertOrchestrator — the pipeline that turns a raw alert dict into a Telegram message.

Pipeline: alert payload → user message → LLM (with Motor context in system prompt) → text

All decisions in the alert payload (projected_ratio, risk_level, earnings, secondary_zones)
are pre-computed by EarlyAlertsAPI using calibrated rules from Motor_Reglas_y_Alertas.md.
The LLM narrates the "why" using that same document injected into the system prompt.
"""
from __future__ import annotations

import logging

from app.agent.context_source import ContextSourceService
from app.agent.llm.client import LLMClient
from app.agent.prompts.system_prompt import build_user_message, map_risk_display

logger = logging.getLogger(__name__)


class AlertOrchestrator:
    """Wires context service + LLM client to produce alert messages."""

    def __init__(
        self,
        context_service: ContextSourceService,
        llm_client: LLMClient,
        system_prompt: str,
    ) -> None:
        self._context = context_service
        self._llm = llm_client
        self._system_prompt = system_prompt

    async def process_alert(self, alert: dict) -> str:
        """Take a raw alert dict from the outbox, return the Telegram message text."""
        risk_level = alert.get("risk_level", "")
        risk_display = map_risk_display(risk_level)
        user_message = build_user_message(alert, risk_display)

        logger.info(
            "Calling LLM for alert %s (zone=%s, risk=%s)",
            alert.get("id"), alert.get("zone"), risk_display,
        )
        return await self._llm.generate(self._system_prompt, user_message)
