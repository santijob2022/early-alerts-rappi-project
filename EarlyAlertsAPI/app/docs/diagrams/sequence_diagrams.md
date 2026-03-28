# Sequence Diagrams

## SD-1 – Full alert cycle (`run_cycle`)

Shows one complete execution of the orchestrator cycle, from scheduler trigger to outbox write.

```mermaid
sequenceDiagram
    autonumber
    participant Scheduler
    participant Orchestrator as Orchestrator (run_cycle)
    participant Provider as OpenMeteo Provider
    participant OpenMeteo as Open-Meteo API
    participant Normalizer
    participant Pipeline as dlt Pipeline
    participant DuckDB
    participant Engine as Decision Engine (evaluate_zone)
    participant SQLite

    Scheduler->>Orchestrator: run_cycle(settings, rule_pack, zone_catalog, ...)
    Orchestrator->>SQLite: create_run(run_id, city, rule_pack_version)
    Orchestrator->>SQLite: save_config_snapshot(run_id, config_json)

    Orchestrator->>Provider: fetch_hourly_forecast(centroids, hours_ahead=6)
    Provider->>OpenMeteo: GET /v1/forecast?latitude=...&longitude=...
    OpenMeteo-->>Provider: JSON hourly precipitation (14 zones × 6 hours)
    Provider-->>Orchestrator: raw_responses[]

    Orchestrator->>Normalizer: normalize(raw_responses, centroids, catalog, run_id)
    Normalizer-->>Orchestrator: ZoneForecastRow[] (UTC → local time, coord match)

    Orchestrator->>Pipeline: run_pipeline(raw_responses, normalized_rows, run_id)
    Pipeline->>DuckDB: append raw_forecast_snapshots
    Pipeline->>DuckDB: append normalized_zone_forecasts
    Pipeline-->>Orchestrator: snapshot_id

    loop For each of 14 zones
        Orchestrator->>SQLite: get_open_event(city, zone)
        SQLite-->>Orchestrator: open_event | None

        Orchestrator->>Engine: evaluate_zone(DecisionInput, rule_pack, baseline_table, open_event, zone_forecasts, zone_catalog)
        Engine-->>Orchestrator: DecisionOutput (ALERT | WATCH | SUPPRESS)

        alt Decision is ALERT or ESCALATE
            alt No open event
                Orchestrator->>SQLite: open_event(event_id, city, zone, max_risk, max_precip)
                Orchestrator->>SQLite: enqueue_alert(outbox_id, event_id, ...)
            else Open event exists and not suppressed by cooldown
                Orchestrator->>SQLite: update_event(event_id, max_risk, max_precip)
                Orchestrator->>SQLite: enqueue_alert(outbox_id, event_id, ...)
            end
        else Decision is SUPPRESS (dry)
            Orchestrator->>SQLite: increment_dry_streak(event_id)
            alt dry_streak >= close_streak_hours (2)
                Orchestrator->>SQLite: close_event(event_id)
            end
        else Decision is WATCH
            Orchestrator->>SQLite: reset_dry_streak(event_id) [if open]
        end

        Orchestrator->>SQLite: record_decision(decision_id, run_id, zone, ...)
    end

    Note over Orchestrator: Watchlist scan: t+2 and t+3
    Orchestrator->>SQLite: record_decision(watch) [for each zone above trigger at t+2/t+3]

    Orchestrator->>SQLite: finish_run(run_id, status="ok", zones, alerts)
    Orchestrator-->>Scheduler: RunSummary(run_id, status, zones_evaluated, alerts_emitted)
```

---

## SD-2 – Module 3 outbox consumption

Shows how Module 3 (Telegram Bot) reads from the outbox without re-running weather logic.

```mermaid
sequenceDiagram
    autonumber
    participant Module3 as Module 3 (Telegram Bot)
    participant SQLite
    participant LLM as LLM (prose generation)
    participant Telegram

    Module3->>SQLite: get_pending_alerts() WHERE status='pending'
    SQLite-->>Module3: alert_outbox rows[]

    loop For each pending alert
        Module3->>LLM: generate_message(zone, risk_level, precip_mm, recommended_earnings_mxn, secondary_zones, ...)
        LLM-->>Module3: Telegram prose (Spanish)
        Module3->>Telegram: send_message(chat_id, prose)
        Telegram-->>Module3: 200 OK
        Module3->>SQLite: mark_consumed(outbox_id)
    end
```

---

## SD-3 – API request: GET /alerts/latest

Shows the synchronous read path through the REST API.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client (Ops / Dashboard)
    participant FastAPI
    participant AlertsRouter as alerts.py router
    participant repo_outbox
    participant SQLite

    Client->>FastAPI: GET /api/v1/alerts/latest?limit=20
    FastAPI->>AlertsRouter: handle request
    AlertsRouter->>repo_outbox: get_pending_alerts(conn, limit)
    repo_outbox->>SQLite: SELECT * FROM alert_outbox WHERE status='pending' ORDER BY created_at DESC
    SQLite-->>repo_outbox: rows
    repo_outbox-->>AlertsRouter: list[dict]
    AlertsRouter-->>FastAPI: JSON response
    FastAPI-->>Client: 200 OK [{"zone": "Santiago", "risk_level": "critico", ...}]
```

---

## SD-4 – POST /jobs/run-once (manual trigger)

Shows how a developer or operator triggers a single alert cycle via the REST API.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client (Developer / CI)
    participant FastAPI
    participant JobsRouter as jobs.py router
    participant Orchestrator as run_cycle()
    participant OpenMeteo as Open-Meteo API
    participant SQLite
    participant DuckDB

    Client->>FastAPI: POST /api/v1/jobs/run-once
    FastAPI->>JobsRouter: handle request
    JobsRouter->>Orchestrator: await run_cycle(settings, rule_pack, zone_catalog, baseline_table, provider, conn)

    Note over Orchestrator,DuckDB: Full cycle executes (same as SD-1)
    Orchestrator->>OpenMeteo: fetch forecast
    Orchestrator->>DuckDB: persist raw + normalized rows
    Orchestrator->>SQLite: write decisions, events, outbox entries
    Orchestrator-->>JobsRouter: RunSummary

    JobsRouter-->>FastAPI: JSON RunSummary
    FastAPI-->>Client: 200 OK {"run_id": "...", "status": "ok", "zones_evaluated": 14, "alerts_emitted": 2}
```

---

## SD-5 – Startup (FastAPI lifespan)

Shows how the application initialises resources when the process starts.

```mermaid
sequenceDiagram
    autonumber
    participant Process as Python Process (uvicorn / early-alerts serve)
    participant Lifespan as FastAPI lifespan()
    participant Config as get_settings()
    participant DB as init_db()
    participant RulePack as load_rule_pack()
    participant ZoneCatalog as load_zone_catalog()
    participant BaselineFile as baseline_ratios.yaml
    participant Scheduler as start_scheduler()

    Process->>Lifespan: startup event
    Lifespan->>Config: get_settings() [lru_cache – YAML + env overrides]
    Config-->>Lifespan: Settings

    Lifespan->>DB: init_db(sqlite_path) [creates tables if not exist]
    Lifespan->>RulePack: load_rule_pack(rule_pack_path)
    RulePack-->>Lifespan: RulePack
    Lifespan->>ZoneCatalog: load_zone_catalog(zone_catalog_path)
    ZoneCatalog-->>Lifespan: ZoneCatalog
    Lifespan->>BaselineFile: yaml.safe_load(baseline_ratios.yaml)
    BaselineFile-->>Lifespan: baseline_table dict

    Lifespan->>Lifespan: app.state.settings / rule_pack / zone_catalog / baseline_table

    alt EARLY_ALERTS_ENABLE_SCHEDULER == true
        Lifespan->>Scheduler: start_scheduler(app)
        Scheduler-->>Lifespan: APScheduler instance running
    else
        Note over Lifespan: Scheduler NOT started (API-only worker)
    end

    Lifespan-->>Process: app ready, serving requests
```
