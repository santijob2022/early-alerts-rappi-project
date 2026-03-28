# C4 — Code Diagram

> Deepest level of the C4 model. Shows the internal structure of the key components: classes, methods, data structures, and their relationships.

## 4.1 Agent Layer — Core Pipeline

```mermaid
classDiagram
    direction TB

    class Settings {
        +str telegram_bot_token
        +str telegram_chat_id
        +str llm_model = "gpt-4o-mini"
        +str llm_api_key
        +str|None llm_api_base
        +str alerts_api_base_url = "http://localhost:8000"
        +int poll_interval_seconds = 120
        +str summary_report_path
        +str csv_rain_bucket_path
        +str csv_zone_sensitivity_path
        +str csv_zone_hour_saturation_path
        +str csv_earnings_interaction_path
    }

    class ContextSourceService {
        -Settings _settings
        -str _summary
        -DataFrame _rain_bucket_df
        -DataFrame _zone_sensitivity_df
        -DataFrame _zone_hour_df
        -DataFrame _earnings_df
        -dict~str,dict~ _rain_bucket_idx
        -dict~str,dict~ _zone_sensitivity_idx
        -dict~str,int~ _zone_sensitivity_rank
        -dict~tuple,dict~ _zone_hour_idx
        -dict~tuple,dict~ _earnings_idx
        +__init__(settings: Settings)
        -_load(settings: Settings) void
        +get_summary_report() str
        +get_historical_context(zone: str, hour: int, precip_mm: float) dict
        +reload() void
    }

    class LLMClient {
        -str _model
        -str _api_key
        -str|None _api_base
        +__init__(settings: Settings)
        +generate(system_prompt: str, user_message: str) str
    }

    class AlertOrchestrator {
        -ContextSourceService _context
        -LLMClient _llm
        -str _system_prompt
        +__init__(context_service, llm_client, system_prompt)
        +process_alert(alert: dict) str
    }

    AlertOrchestrator --> ContextSourceService : uses
    AlertOrchestrator --> LLMClient : uses
    ContextSourceService --> Settings : reads paths from
    LLMClient --> Settings : reads model config from

    note for ContextSourceService "Lookup dicts:\n_rain_bucket_idx[bucket] → row\n_zone_sensitivity_idx[zone] → row\n_zone_hour_idx[(zone,hour)] → row\n_earnings_idx[(Q,bucket)] → row"
```

## 4.2 Services Layer — External Integrations

```mermaid
classDiagram
    direction TB

    class AlertsAPIConsumer {
        -str _base
        +__init__(base_url: str)
        +fetch_pending_alerts() list~dict~
        +trigger_run_once() dict
        +mark_consumed(alert_id: str) void
        +get_health() dict
    }

    class TelegramSender {
        <<module>>
        +send_message(bot_token: str, chat_id: str, text: str) bool
        -_truncate(text: str) str
    }

    class TelegramCommands {
        <<module>>
        +build_application(bot_token, chat_id, consumer, orchestrator) Application
        -check(update, context) void
        -force_check(update, context) void
        -status(update, context) void
        -_process_and_send(update, alerts, health, orchestrator, consumer, bot_token, chat_id) void
        -_fmt_baixo_response(health: dict) str
    }

    class AlertOrchestrator {
        +process_alert(alert: dict) str
    }

    TelegramCommands --> AlertsAPIConsumer : fetch, trigger, consume
    TelegramCommands --> AlertOrchestrator : process_alert()
    TelegramCommands --> TelegramSender : send_message()

    note for AlertsAPIConsumer "Endpoints:\nGET /alerts/latest?status=pending\nPATCH /alerts/{id}/consume\nPOST /jobs/run-once\nGET /health"
    note for TelegramSender "Truncates at 4096 chars\nUses httpx POST to Bot API"
```

## 4.3 Prompt Engineering — Templates and Formatting

```mermaid
classDiagram
    direction TB

    class PromptBuilder {
        <<module: app.agent.prompts.system_prompt>>
        +build_system_prompt(historical_summary: str) str
        +build_user_message(alert: dict, ctx: dict, risk_display: str, hour: int) str
        +map_risk_display(risk_level: str) str
    }

    class SystemPromptTemplate {
        <<constant>>
        +SYSTEM_PROMPT_TEMPLATE: str
        sections: Rol, Reglas, Contexto Histórico
    }

    class UserMessageTemplate {
        <<constant>>
        +USER_MESSAGE_TEMPLATE: str
        fields: zone, risk, precip, ratio, earnings, ventana, zonas_secundarias, contexto_historico
    }

    class UserMessageFallback {
        <<constant>>
        +USER_MESSAGE_MISSING_HISTORY: str
        note: "Used when historical context incomplete"
    }

    class RiskDisplayMap {
        <<constant>>
        +"medio" → "MEDIO"
        +"alto" → "ALTO"
        +"critico" → "CRÍTICO"
        +default → upper()
    }

    PromptBuilder --> SystemPromptTemplate : formats with historical_summary
    PromptBuilder --> UserMessageTemplate : formats when has_history=True
    PromptBuilder --> UserMessageFallback : formats when has_history=False
    PromptBuilder --> RiskDisplayMap : lookups risk_level

    note for UserMessageTemplate "has_history = True when ALL of:\n- zone_sensitivity_rank ≠ None\n- zone_hour_pct_saturated ≠ None\n- earnings_q4_pct_saturated ≠ None\n- earnings_q2_pct_saturated ≠ None"
```

## 4.4 Data Flow — Historical Context Lookup

```mermaid
flowchart LR
    subgraph Input
        A[zone: str]
        B[hour: int]
        C[precip_mm: float]
    end

    C -->|_classify_rain| D{Rain Bucket}
    D -->|"no_rain / light / moderate / heavy"| E

    subgraph "Lookup Dicts (O1)"
        E[_rain_bucket_idx<br/>key: bucket] --> F[city_avg_ratio<br/>city_pct_saturated]
        A --> G[_zone_sensitivity_idx<br/>key: zone] --> H[ratio_lift<br/>sensitivity_rank]
        A --> I["_zone_hour_idx<br/>key: (zone, hour)"]
        B --> I --> J[zone_hour_pct_saturated<br/>zone_hour_avg_ratio]
        E --> K["_earnings_idx<br/>key: (Q4_high, bucket)"]
        E --> L["_earnings_idx<br/>key: (Q2, bucket)"]
        K --> M[earnings_q4_pct_saturated]
        L --> N[earnings_q2_pct_saturated]
    end

    subgraph Output
        O[ctx: dict<br/>12 fields]
    end

    F --> O
    H --> O
    J --> O
    M --> O
    N --> O
```

## 4.5 Rain Bucket Classification

```mermaid
flowchart LR
    P[precip_mm] --> Q{">= 7.5?"}
    Q -->|Yes| R["heavy"]
    Q -->|No| S{">= 2.5?"}
    S -->|Yes| T["moderate"]
    S -->|No| U{">= 0.1?"}
    U -->|Yes| V["light"]
    U -->|No| W["no_rain"]
```

| Bucket | Rango (mm/hr) |
|---|---|
| `no_rain` | 0.0 – 0.1 |
| `light` | 0.1 – 2.5 |
| `moderate` | 2.5 – 7.5 |
| `heavy` | ≥ 7.5 |
