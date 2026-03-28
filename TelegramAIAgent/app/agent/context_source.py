"""ContextSourceService — loads the decision-engine rule documents.

All file I/O happens here. Paths come from Settings so they can be
overridden via env vars or .env without touching code.

The Motor documents (Motor_Reglas_y_Alertas.md + Documentacion_Motor_Alertas_Tempranas.md)
already synthesise all Module 1 historical findings (M1-P1 through M1-P5) and CALC-1
calibration into rules with full traceability. They are the canonical source of truth
for the LLM system prompt — no CSV re-processing needed.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)


class ContextSourceService:
    """Loads Motor rule documents and serves them for LLM prompt construction."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._load(settings)

    def _load(self, settings: Settings) -> None:
        logger.info("Loading Motor rule documents from configured paths...")
        self._motor_rules = Path(settings.motor_rules_path).read_text(encoding="utf-8")
        self._motor_docs = Path(settings.motor_docs_path).read_text(encoding="utf-8")
        logger.info("Motor documents loaded successfully.")

    def get_motor_context(self) -> str:
        """Return the combined Motor context for injection into the LLM system prompt.

        Motor_Reglas_y_Alertas.md provides full calibration detail (all thresholds,
        lifts, earnings targets, stats). Documentacion_Motor_Alertas_Tempranas.md
        provides the compact operational summary.
        """
        return self._motor_rules + "\n\n---\n\n" + self._motor_docs

    def reload(self) -> None:
        """Re-read documents from their current configured paths.

        Call after updating path settings at runtime.
        """
        self._load(self._settings)
