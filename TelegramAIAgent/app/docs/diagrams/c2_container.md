# C2 — Container Diagram

> Zooms into the TelegramAIAgent system boundary, showing the containers (deployable units) and how they communicate.

```mermaid
C4Container
    title Container Diagram — TelegramAIAgent (Module 3)

    Person(ops_manager, "Gerente de Operaciones", "Recibe alertas operativas via Telegram")

    System_Boundary(telegram_agent_system, "TelegramAIAgent System") {
        Container(agent_app, "TelegramAIAgent App", "Python 3.13, asyncio", "Aplicación principal: poll loop automático + listener de comandos Telegram. Orquesta el flujo completo de alertas.")
        ContainerDb(historical_data, "Historical Context Data", "CSV + Markdown files", "4 tablas CSV (rain buckets, sensibilidad por zona, saturación zona×hora, interacción earnings×lluvia) + resumen de hallazgos en Markdown")
        Container(docker_runtime, "Docker Container", "python:3.13-slim", "Entorno de ejecución containerizado con docker-compose")
    }

    System_Ext(early_alerts_api, "EarlyAlertsAPI", "Module 2 — Motor de decisión de alertas tempranas (FastAPI + DuckDB + SQLite)")
    System_Ext(telegram_api, "Telegram Bot API", "api.telegram.org — Plataforma de mensajería")
    System_Ext(llm_provider, "LLM Provider", "OpenAI / Anthropic / Ollama via LiteLLM")

    Rel(ops_manager, agent_app, "Envía /check, /force_check, /status", "Telegram Bot Commands")
    Rel(agent_app, ops_manager, "Envía alertas narrativas", "Telegram Messages")

    Rel(agent_app, early_alerts_api, "GET /alerts/latest, PATCH /alerts/{id}/consume, POST /jobs/run-once, GET /health", "HTTP/REST (httpx)")
    Rel(agent_app, telegram_api, "POST /sendMessage", "HTTPS (httpx)")
    Rel(agent_app, llm_provider, "Chat completion (system + user prompt)", "HTTPS (LiteLLM)")
    Rel(agent_app, historical_data, "Lee al inicio y por demanda", "File I/O (pandas)")
```

## Containers

| Container | Tecnología | Responsabilidad |
|---|---|---|
| **TelegramAIAgent App** | Python 3.13, asyncio, pydantic-settings | Proceso principal que ejecuta dos tareas concurrentes: (1) poll loop automático cada N segundos, (2) listener de comandos Telegram. Contiene la lógica de orquestación, integración con LLM, y envío de mensajes. |
| **Historical Context Data** | 4 CSV + 1 Markdown | Datos estáticos del Módulo 1 de análisis (30 días históricos de Monterrey). Cargados en memoria al inicio. Rutas configurables via env vars. |
| **Docker Container** | python:3.13-slim, docker-compose | Empaquetado de la aplicación. Se conecta a la red Docker de EarlyAlertsAPI. |

## Comunicación entre Containers

| Origen | Destino | Protocolo | Detalle |
|---|---|---|---|
| Agent App | EarlyAlertsAPI | HTTP REST | 4 endpoints: fetch pending, consume, run-once, health |
| Agent App | Telegram Bot API | HTTPS | `POST /sendMessage` para enviar alertas |
| Agent App | LLM Provider | HTTPS | `litellm.acompletion()` — provider-agnostic |
| Agent App | Historical Data | File I/O | `pandas.read_csv()` + `Path.read_text()` al startup |
