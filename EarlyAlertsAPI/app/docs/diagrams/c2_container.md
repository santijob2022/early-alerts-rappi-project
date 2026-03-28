# C2 – Container Diagram

Shows the **processes, services, and data stores** that make up EarlyAlertsAPI.

```mermaid
C4Container
    title Container Diagram – EarlyAlertsAPI

    Person(ops, "Operations Team")
    System_Ext(openMeteo, "Open-Meteo API")
    System_Ext(module3, "Module 3 – Telegram Bot")

    System_Boundary(earlyAlerts, "EarlyAlertsAPI") {

        Container(apiContainer, "API Container", "Python / FastAPI + Uvicorn", "Serves REST endpoints: /health, /config, /alerts/latest, /events/open, /jobs/run-once. EARLY_ALERTS_ENABLE_SCHEDULER=false.")

        Container(schedulerContainer, "Scheduler Container", "Python / APScheduler + Typer", "Runs early-alerts serve. Triggers orchestrator on an adaptive interval (60 min default / 15 min elevated). EARLY_ALERTS_ENABLE_SCHEDULER=true.")

        ContainerDb(sqliteDb, "SQLite", "SQLite file (alerts.db)", "Transactional application state: pipeline_runs, alert_events, decision_records, alert_outbox, effective_config_snapshots.")

        ContainerDb(duckDb, "DuckDB", "DuckDB file via dlt (forecast_warehouse.duckdb)", "Append-only analytical store: raw_forecast_snapshots, normalized_zone_forecasts. Full ingestion history.")

        Container(configFiles, "YAML Config Files", "Static files", "config.yaml, rule_pack_v1.yaml, monterrey_zones.yaml, baseline_ratios.yaml. Loaded once at startup.")
    }

    Rel(ops, apiContainer, "Reads monitoring data", "HTTP REST")
    Rel(schedulerContainer, openMeteo, "Fetches hourly forecast", "HTTPS")
    Rel(schedulerContainer, duckDb, "Writes raw + normalized rows", "dlt / DuckDB driver")
    Rel(schedulerContainer, sqliteDb, "Writes runs, events, decisions, outbox", "SQLAlchemy Core")
    Rel(apiContainer, sqliteDb, "Reads events, alerts, run status", "SQLAlchemy Core")
    Rel(apiContainer, configFiles, "Loads at startup", "File I/O")
    Rel(schedulerContainer, configFiles, "Loads at startup", "File I/O")
    Rel(module3, sqliteDb, "Polls alert_outbox, calls mark_consumed", "SQLite")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Storage split rationale

| Store | Technology | Responsibility |
|---|---|---|
| **SQLite** | SQLAlchemy Core | Low-latency transactional state (events, outbox, runs). Single-writer, crash-safe. |
| **DuckDB** (via dlt) | dlt + DuckDB driver | Append-only analytical history. Full raw + normalised forecast archive for replay and dashboards. |

The two stores are independent failure domains: DuckDB ingest failure is non-fatal to the alert cycle.

## Scheduler singleton pattern

`EARLY_ALERTS_ENABLE_SCHEDULER` controls whether a process starts APScheduler.  
In Docker Compose the **scheduler** service sets it `true`; all **api** workers leave it `false`.  
This prevents duplicate `run_cycle()` calls.
