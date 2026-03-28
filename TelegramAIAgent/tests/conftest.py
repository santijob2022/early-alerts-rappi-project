"""Shared fixtures for the TelegramAIAgent test suite."""
from __future__ import annotations

import pytest

from app.config import Settings


RULES_CONTENT = """\
# Motor Reglas y Alertas (test fixture)

## Umbrales de precipitación
- Lluvia base: 2.0 mm/hr
- Zona sensible en pico: 1.0 mm/hr

## Earnings objetivo
- Q4 histórico: 80 MXN

## Zonas — ranking sensibilidad
1. Santiago (ratio_lift=1.82, [M1-P3])
2. Carretera Nacional (ratio_lift=1.65, [M1-P3])
"""

DOCS_CONTENT = """\
# Documentacion Motor Alertas Tempranas (test fixture)

Resumen ejecutivo del motor de decisión.
Umbral base: 2.0 mm/hr. Earnings recomendado: 80 MXN.
"""

MINIMAL_ALERT: dict = {
    "id": "alert-001",
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


@pytest.fixture()
def motor_files(tmp_path):
    """Write the two Motor markdown files to tmp_path and return their paths."""
    rules = tmp_path / "Motor_Reglas_y_Alertas.md"
    docs = tmp_path / "Documentacion_Motor_Alertas_Tempranas.md"
    rules.write_text(RULES_CONTENT, encoding="utf-8")
    docs.write_text(DOCS_CONTENT, encoding="utf-8")
    return rules, docs


@pytest.fixture()
def test_settings(motor_files):
    """A Settings instance pointing at tmp Motor files (no real .env needed)."""
    rules, docs = motor_files
    return Settings(
        telegram_bot_token="test_bot_token",
        telegram_chat_id="test_chat_id",
        llm_api_key="test_api_key",
        motor_rules_path=str(rules),
        motor_docs_path=str(docs),
    )
