# Rapi — Early Alerts Project

This repository groups three related components for an early-alerts system:

- DataAnalysis: notebooks and scripts used to analyze historical data, calibrate thresholds, and produce baseline statistics used by the decision engine.
- EarlyAlertsAPI: FastAPI backend implementing the decision engine, ingestion, persistence (SQLite/DuckDB) and alert lifecycle handling.
- TelegramAIAgent: Telegram-based notifier that reads alert outputs and sends formatted messages to a configured chat.

Each component lives in its own subfolder and can be used independently.
