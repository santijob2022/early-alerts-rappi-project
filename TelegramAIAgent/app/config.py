"""Centralised settings for TelegramAIAgent.

All configuration is read from environment variables or a .env file.
Context source paths are intentionally kept as plain strings so that they can
be overridden without any code changes — update the env var and restart.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Telegram ─────────────────────────────────────────────────────────────
    telegram_bot_token: str
    telegram_chat_id: str

    # ── LLM (LiteLLM — any provider) ─────────────────────────────────────────
    # Model string in LiteLLM format, e.g. "gpt-4o-mini",
    # "anthropic/claude-3-haiku-20240307", "ollama/llama3"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str
    # Optional: custom API base (Azure, Ollama, etc.)
    llm_api_base: str | None = None

    # ── EarlyAlertsAPI ────────────────────────────────────────────────────────
    alerts_api_base_url: str = "http://localhost:8000"
    # How often the poll loop checks for new pending alerts (seconds)
    poll_interval_seconds: int = 120

    # ── Display preferences ──────────────────────────────────────────────────
    # IANA timezone name used when formatting timestamps in Telegram messages.
    # Examples: America/Mexico_City, America/New_York, Europe/Madrid, UTC
    display_timezone: str = "America/Mexico_City"

    # ── Context source paths (configurable — no code change needed) ───────────
    # Detailed rule calibration document — injected into LLM system prompt.
    # Contains all thresholds, lifts, earnings targets and historical stats from
    # Module 1 analysis and CALC-1 notebook, already synthesised into rules.
    motor_rules_path: str = "data/historical_context/Motor_Reglas_y_Alertas.md"
    # Compact summary document — appended after the rules for executive context.
    motor_docs_path: str = "data/historical_context/Documentacion_Motor_Alertas_Tempranas.md"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
