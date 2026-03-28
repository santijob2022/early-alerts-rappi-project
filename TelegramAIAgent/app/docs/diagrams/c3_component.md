# C3 — Component Diagram

> Zooms into the TelegramAIAgent App container, showing the internal components (modules) and their interactions.

```mermaid
C4Component
    title Component Diagram — TelegramAIAgent App

    Container_Boundary(agent_app, "TelegramAIAgent App") {

        Component(main, "Main Entrypoint", "app.main", "Wires all services, starts concurrent poll loop + Telegram listener via asyncio")
        Component(config, "Settings", "app.config (pydantic-settings)", "Centralised configuration from env vars / .env file")

        Component_Ext(poll_loop, "Poll Loop", "app.main.poll_loop()", "Async loop: every N seconds fetches pending alerts, processes, sends, acks")

        Component(orchestrator, "AlertOrchestrator", "app.agent.orchestrator", "Pipeline: alert → context enrichment → prompt build → LLM call → formatted text")
        Component(context_source, "ContextSourceService", "app.agent.context_source", "Loads historical CSV + MD data from configurable paths into in-memory lookup dicts")
        Component(prompt_builder, "Prompt Builder", "app.agent.prompts.system_prompt", "Builds system prompt (with historical summary) and per-alert user messages")
        Component(llm_client, "LLMClient", "app.agent.llm.client", "Provider-agnostic LLM wrapper using LiteLLM (acompletion)")

        Component(alerts_consumer, "AlertsAPIConsumer", "app.services.alerts_api.consumer", "HTTP client: fetch pending, mark consumed, trigger run-once, health check")
        Component(telegram_sender, "Telegram Sender", "app.services.telegram.sender", "Sends messages via Telegram Bot API HTTP endpoint")
        Component(telegram_commands, "Telegram Commands", "app.services.telegram.commands", "Handlers for /check, /force_check, /status using python-telegram-bot")
    }

    System_Ext(early_alerts_api, "EarlyAlertsAPI", "Module 2 — Motor de decisión")
    System_Ext(telegram_api, "Telegram Bot API", "api.telegram.org")
    System_Ext(llm_provider, "LLM Provider", "OpenAI / Anthropic / Ollama")
    ContainerDb(historical_data, "Historical Context Data", "CSV + MD files")

    Rel(main, config, "Reads configuration")
    Rel(main, orchestrator, "Creates and injects")
    Rel(main, alerts_consumer, "Creates")
    Rel(main, telegram_commands, "Builds Application with handlers")
    Rel(main, poll_loop, "Starts as concurrent task")

    Rel(poll_loop, alerts_consumer, "fetch_pending_alerts()")
    Rel(poll_loop, orchestrator, "process_alert(alert)")
    Rel(poll_loop, telegram_sender, "send_message()")
    Rel(poll_loop, alerts_consumer, "mark_consumed(alert_id)")

    Rel(telegram_commands, alerts_consumer, "fetch_pending, trigger_run_once, get_health")
    Rel(telegram_commands, orchestrator, "process_alert(alert)")
    Rel(telegram_commands, telegram_sender, "send_message()")

    Rel(orchestrator, context_source, "get_historical_context(zone, hour, precip_mm)")
    Rel(orchestrator, prompt_builder, "build_user_message(alert, ctx, risk, hour)")
    Rel(orchestrator, llm_client, "generate(system_prompt, user_message)")

    Rel(context_source, historical_data, "pandas.read_csv(), Path.read_text()")
    Rel(prompt_builder, historical_data, "Historical summary injected into system prompt")

    Rel(alerts_consumer, early_alerts_api, "HTTP/REST (httpx)")
    Rel(telegram_sender, telegram_api, "POST /sendMessage (httpx)")
    Rel(llm_client, llm_provider, "litellm.acompletion()")
```

## Components

| Componente | Módulo | Responsabilidad |
|---|---|---|
| **Main Entrypoint** | `app.main` | Punto de entrada. Instancia todos los servicios, construye el system prompt, arranca el poll loop y el listener de Telegram concurrentemente con `asyncio`. |
| **Settings** | `app.config` | Configuración centralizada con `pydantic-settings`. Lee de `.env` o variables de entorno. Incluye tokens, modelo LLM, URL de la API, intervalo de polling, y rutas de archivos de contexto. |
| **Poll Loop** | `app.main.poll_loop()` | Bucle infinito asíncrono. Cada `poll_interval_seconds` consulta alertas pendientes, las procesa por el pipeline completo, y las marca como consumidas. |
| **AlertOrchestrator** | `app.agent.orchestrator` | Pipeline central: recibe un alert dict crudo → extrae hora → obtiene contexto histórico → construye user message → llama al LLM → retorna texto formateado para Telegram. |
| **ContextSourceService** | `app.agent.context_source` | Carga los 4 CSV y 1 Markdown al inicio desde rutas configurables. Construye dicts indexados para lookup O(1) por zona, hora, bucket de lluvia, y cuartil de earnings. Método `reload()` para actualización en runtime. |
| **Prompt Builder** | `app.agent.prompts.system_prompt` | Construye el system prompt (inyecta resumen histórico) y el user message por alerta. Incluye template completo (con historia) y fallback (sin historia). Mapea niveles de riesgo a display labels. |
| **LLMClient** | `app.agent.llm.client` | Wrapper sobre `litellm.acompletion()`. Provider-agnostic: cambiar de OpenAI a Anthropic/Ollama requiere solo cambiar env vars. Timeout de 30s. |
| **AlertsAPIConsumer** | `app.services.alerts_api.consumer` | Cliente HTTP para EarlyAlertsAPI. 4 métodos: `fetch_pending_alerts()`, `mark_consumed()`, `trigger_run_once()`, `get_health()`. Usa `httpx.AsyncClient`. |
| **Telegram Sender** | `app.services.telegram.sender` | Función `send_message()` que envía texto plano via Bot API. Trunca a 4096 chars (límite Telegram). Manejo de errores con logging. |
| **Telegram Commands** | `app.services.telegram.commands` | Registra handlers para `/check`, `/force_check`, `/status` en una `Application` de python-telegram-bot. Cada comando ejecuta el mismo pipeline que el poll loop. |
