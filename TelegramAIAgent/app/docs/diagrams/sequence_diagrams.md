# Sequence Diagrams

> Shows the step-by-step message flow for the two main operational scenarios: automatic polling and manual Telegram commands.

## 1. Auto Poll Loop — Automatic Alert Processing

```mermaid
sequenceDiagram
    autonumber
    participant Main as main.py<br/>(poll_loop)
    participant Consumer as AlertsAPIConsumer
    participant API as EarlyAlertsAPI
    participant Orch as AlertOrchestrator
    participant Ctx as ContextSourceService
    participant Prompt as PromptBuilder
    participant LLM as LLMClient
    participant LLMProv as LLM Provider<br/>(GPT-4o-mini)
    participant Sender as TelegramSender
    participant TgAPI as Telegram Bot API
    participant Ops as Gerente de<br/>Operaciones

    loop Every poll_interval_seconds (default: 120s)
        Main->>Consumer: fetch_pending_alerts()
        Consumer->>API: GET /api/v1/alerts/latest?status=pending&limit=50
        API-->>Consumer: [alert_1, alert_2, ...]
        Consumer-->>Main: list[dict]

        alt No pending alerts
            Main->>Main: sleep(poll_interval_seconds)
        else Has pending alerts
            loop For each alert
                Main->>Orch: process_alert(alert)

                Orch->>Orch: _extract_hour(alert.forecast_time)
                Orch->>Ctx: get_historical_context(zone, hour, precip_mm)
                Ctx->>Ctx: _classify_rain(precip_mm) → rain_bucket
                Ctx->>Ctx: Lookup: _rain_bucket_idx[bucket]
                Ctx->>Ctx: Lookup: _zone_sensitivity_idx[zone]
                Ctx->>Ctx: Lookup: _zone_hour_idx[(zone, hour)]
                Ctx->>Ctx: Lookup: _earnings_idx[(Q4_high, bucket)]
                Ctx->>Ctx: Lookup: _earnings_idx[(Q2, bucket)]
                Ctx-->>Orch: ctx: dict (12 fields)

                Orch->>Prompt: map_risk_display(risk_level)
                Prompt-->>Orch: risk_display (e.g. "ALTO")
                Orch->>Prompt: build_user_message(alert, ctx, risk_display, hour)
                Prompt-->>Orch: user_message: str

                Orch->>LLM: generate(system_prompt, user_message)
                LLM->>LLMProv: litellm.acompletion(model, messages, api_key)
                LLMProv-->>LLM: ChatCompletion response
                LLM-->>Orch: formatted_text: str
                Orch-->>Main: text: str

                Main->>Sender: send_message(bot_token, chat_id, text)
                Sender->>TgAPI: POST /sendMessage
                TgAPI-->>Sender: 200 OK
                TgAPI->>Ops: Push notification 📱
                Sender-->>Main: True

                Main->>Consumer: mark_consumed(alert.id)
                Consumer->>API: PATCH /api/v1/alerts/{id}/consume
                API-->>Consumer: {"status": "consumed"}
                Consumer-->>Main: void
            end
        end
        Main->>Main: sleep(poll_interval_seconds)
    end
```

## 2. Manual Command — /check

```mermaid
sequenceDiagram
    autonumber
    participant Ops as Gerente de<br/>Operaciones
    participant TgAPI as Telegram Bot API
    participant Cmds as TelegramCommands<br/>(/check handler)
    participant Consumer as AlertsAPIConsumer
    participant API as EarlyAlertsAPI
    participant Orch as AlertOrchestrator
    participant LLM as LLMClient
    participant Sender as TelegramSender

    Ops->>TgAPI: /check
    TgAPI->>Cmds: Update (command: check)
    Cmds->>Ops: "🔍 Consultando alertas pendientes..."

    Cmds->>Consumer: fetch_pending_alerts()
    Consumer->>API: GET /api/v1/alerts/latest?status=pending
    API-->>Consumer: [alerts]
    Consumer-->>Cmds: list[dict]

    Cmds->>Consumer: get_health()
    Consumer->>API: GET /api/v1/health
    API-->>Consumer: health dict
    Consumer-->>Cmds: health

    alt No pending alerts (BAJO)
        Cmds->>Ops: "✅ Sin riesgo inminente — Nivel: BAJO<br/>Última ejecución: {last_run}<br/>Eventos abiertos: {open_events}"
    else Has pending alerts
        loop For each alert
            Cmds->>Orch: process_alert(alert)
            Orch->>LLM: generate(system_prompt, user_message)
            LLM-->>Orch: formatted_text
            Orch-->>Cmds: text

            Cmds->>Sender: send_message(bot_token, chat_id, text)
            Sender->>TgAPI: POST /sendMessage
            TgAPI->>Ops: Alert message 📱

            Cmds->>Consumer: mark_consumed(alert.id)
            Consumer->>API: PATCH /api/v1/alerts/{id}/consume
        end
    end
```

## 3. Manual Command — /force_check

```mermaid
sequenceDiagram
    autonumber
    participant Ops as Gerente de<br/>Operaciones
    participant TgAPI as Telegram Bot API
    participant Cmds as TelegramCommands<br/>(/force_check handler)
    participant Consumer as AlertsAPIConsumer
    participant API as EarlyAlertsAPI
    participant Orch as AlertOrchestrator
    participant LLM as LLMClient
    participant Sender as TelegramSender

    Ops->>TgAPI: /force_check
    TgAPI->>Cmds: Update (command: force_check)
    Cmds->>Ops: "⚡ Ejecutando ciclo de evaluación..."

    Cmds->>Consumer: trigger_run_once()
    Consumer->>API: POST /api/v1/jobs/run-once
    Note over API: Executes full cycle:<br/>fetch forecast → evaluate zones<br/>→ emit alerts to outbox
    API-->>Consumer: {"alerts_emitted": N}
    Consumer-->>Cmds: run_result

    Cmds->>Ops: "Motor ejecutado. Alertas emitidas: {N}. Procesando..."

    Cmds->>Consumer: fetch_pending_alerts()
    Consumer->>API: GET /api/v1/alerts/latest?status=pending
    API-->>Consumer: [alerts]

    Cmds->>Consumer: get_health()
    Consumer->>API: GET /api/v1/health
    API-->>Consumer: health

    alt No pending alerts (BAJO)
        Cmds->>Ops: "✅ Sin riesgo inminente — Nivel: BAJO"
    else Has alerts
        loop For each alert
            Cmds->>Orch: process_alert(alert)
            Orch->>LLM: generate(system_prompt, user_message)
            LLM-->>Orch: text
            Orch-->>Cmds: text

            Cmds->>Sender: send_message(bot_token, chat_id, text)
            Sender->>TgAPI: POST /sendMessage
            TgAPI->>Ops: Alert 📱

            Cmds->>Consumer: mark_consumed(alert.id)
            Consumer->>API: PATCH /api/v1/alerts/{id}/consume
        end
    end
```

## 4. Startup — System Initialization

```mermaid
sequenceDiagram
    autonumber
    participant Env as .env / Env Vars
    participant Main as main()
    participant Config as Settings
    participant Ctx as ContextSourceService
    participant Files as Motor Documents<br/>(MD files)
    participant LLM as LLMClient
    participant Prompt as build_system_prompt()
    participant Orch as AlertOrchestrator
    participant Cmds as build_application()
    participant PollLoop as poll_loop()
    participant TgBot as Telegram Updater

    Main->>Config: Settings()
    Config->>Env: Read env vars / .env
    Env-->>Config: All config values
    Config-->>Main: settings

    Main->>Ctx: ContextSourceService(settings)
    Ctx->>Files: read_text(motor_rules_path)
    Ctx->>Files: read_text(motor_docs_path)
    Files-->>Ctx: Rules MD + Docs MD
    Ctx-->>Main: context_service

    Main->>LLM: LLMClient(settings)
    LLM-->>Main: llm_client

    Main->>Ctx: get_motor_context()
    Ctx-->>Main: motor_context (combined Markdown)
    Main->>Prompt: build_system_prompt(motor_context)
    Prompt-->>Main: system_prompt: str

    Main->>Orch: AlertOrchestrator(context_service, llm_client, system_prompt)
    Orch-->>Main: orchestrator

    Main->>Cmds: build_application(bot_token, chat_id, consumer, orchestrator)
    Cmds-->>Main: tg_app (Application)

    par Concurrent execution
        Main->>TgBot: start_polling(drop_pending_updates=True)
        Note over TgBot: Listens for /check, /force_check, /status
    and
        Main->>PollLoop: poll_loop(settings, consumer, orchestrator)
        Note over PollLoop: Infinite loop: fetch → process → send → ack
    end
```
