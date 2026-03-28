# C3 – Component Diagram

Shows the **components inside the backend Python package** (`app/backend/`).

```mermaid
C4Component
    title Component Diagram – app/backend (Scheduler Container)

    System_Ext(openMeteo, "Open-Meteo API")
    ContainerDb(sqliteDb, "SQLite (alerts.db)")
    ContainerDb(duckDb, "DuckDB (forecast_warehouse.duckdb)")

    Container_Boundary(backend, "app/backend") {

        Component(scheduler, "Scheduler", "services/scheduler.py · APScheduler", "Adaptive interval runner (60 / 15 min). Calls run_cycle() via Orchestrator. Starts only when EARLY_ALERTS_ENABLE_SCHEDULER=true.")

        Component(orchestrator, "Orchestrator", "services/orchestrator.py", "run_cycle(): coordinates fetch → ingest → decide → write. Holds memory logic (cooldown, escalation, dry-close streak). Returns RunSummary.")

        Component(provider, "OpenMeteo Provider", "ingestion/open_meteo.py + provider_base.py", "Sends batch HTTP call for 14 centroids. Falls back to concurrent requests on batch failure. Retries up to max_retries.")

        Component(normalizer, "Normalizer", "ingestion/normalizer.py", "Maps raw JSON responses to ZoneForecastRow list. Handles UTC→local time conversion and coordinate matching.")

        Component(pipeline, "dlt Pipeline", "ingestion/pipeline.py", "Runs dlt pipeline to persist raw_forecast_snapshots and normalized_zone_forecasts into DuckDB. Append-only.")

        Component(engine, "Decision Engine", "decision/engine.py", "evaluate_zone() – pure function. No I/O. Returns DecisionOutput (ALERT / WATCH / SUPPRESS / ESCALATE).")

        Component(projections, "Projections", "decision/projections.py", "project_ratio(): baseline lookup + rain lift + sensitive-peak floor override.")
        Component(severity, "Severity", "decision/severity.py", "classify_risk(): maps projected ratio → RiskLevel (MEDIO / ALTO / CRITICO).")
        Component(earnings, "Earnings", "decision/earnings.py", "recommend_earnings(): returns (target, uplift) against 80 MXN target.")
        Component(secondaryZones, "Secondary Zones", "decision/secondary_zones.py", "rank_secondary_zones(): ranks up to 2 companion zones by sensitivity + precip + distance.")

        Component(stateRepos, "State Repositories", "state/repo_*.py + database.py", "repo_runs, repo_events, repo_decisions, repo_outbox, repo_config. SQLAlchemy Core CRUD over SQLite.")

        Component(config, "Config + Rule Pack", "core/config.py + core/rule_pack.py + core/zone_catalog.py", "pydantic-settings from config.yaml + EARLY_ALERTS_* env overrides. RulePack and ZoneCatalog loaded once at startup.")
    }

    Rel(scheduler, orchestrator, "Calls run_cycle()", "Python function call")
    Rel(orchestrator, provider, "fetch_hourly_forecast(centroids)", "async call")
    Rel(provider, openMeteo, "GET /v1/forecast", "HTTPS")
    Rel(orchestrator, normalizer, "normalize(raw, centroids, catalog)", "Python call")
    Rel(orchestrator, pipeline, "run_pipeline(raw, normalized)", "Python call")
    Rel(pipeline, duckDb, "Appends rows", "dlt / DuckDB")
    Rel(orchestrator, engine, "evaluate_zone(input) per zone", "Python call (pure)")
    Rel(engine, projections, "project_ratio()", "Python call")
    Rel(engine, severity, "classify_risk()", "Python call")
    Rel(engine, earnings, "recommend_earnings()", "Python call")
    Rel(engine, secondaryZones, "rank_secondary_zones()", "Python call")
    Rel(orchestrator, stateRepos, "Reads/writes events, decisions, outbox, runs", "SQLAlchemy Core")
    Rel(stateRepos, sqliteDb, "SQL", "SQLite file")
    Rel(orchestrator, config, "reads settings, rule_pack, zone_catalog", "Python attrs")

    UpdateLayoutConfig($c4ShapeInRow="4", $c4BoundaryInRow="1")
```

## Component summary

| Component | Pattern | CC |
|---|---|---|
| `orchestrator.py` | Coordinator – stateful cycle logic | ≤ B |
| `engine.py` | Pure function – zero I/O | ≤ A |
| `projections.py` | Pure function – baseline lookup + lift | ≤ A |
| `severity.py` | Pure function – threshold lookup | ≤ A |
| `earnings.py` | Pure function – single comparison | ≤ A |
| `secondary_zones.py` | Pure function – sort + slice | ≤ A |
| `scheduler.py` | APScheduler wrapper | ≤ A |
| `repo_*.py` | Repository – SQLAlchemy Core CRUD | ≤ A each |
