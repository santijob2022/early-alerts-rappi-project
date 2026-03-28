# C4 – Code Diagram

Shows the **key classes, models, and call relationships** inside the Decision Engine and Orchestrator components.

## Decision Engine internals

```mermaid
classDiagram
    direction LR

    class DecisionInput {
        +str zone
        +int forecast_hour
        +float forecast_precip_mm
        +int current_hour
        +float current_earnings_mxn
    }

    class DecisionOutput {
        +DecisionType decision_type
        +RiskLevel|None risk_level
        +float|None projected_ratio
        +float recommended_earnings_mxn
        +float uplift_mxn
        +int lead_time_min
        +list[str] secondary_zones
        +str reason
    }

    class DecisionType {
        <<enumeration>>
        ALERT
        WATCH
        SUPPRESS
        ESCALATE
    }

    class RiskLevel {
        <<enumeration>>
        MEDIO
        ALTO
        CRITICO
    }

    class RulePack {
        +str version
        +TriggerSettings triggers
        +list[int] peak_hours
        +list[str] sensitive_zones
        +list[str] volume_monitors
        +RainLifts rain_lifts
        +dict sensitive_peak_floors
        +SeverityThresholds severity_thresholds
        +EarningsSettings earnings
        +MemorySettings memory
        +SecondaryZonesSettings secondary_zones
        +HorizonSettings horizons
    }

    class ZoneCatalog {
        +list[ZoneInfo] zones
        +ZoneInfo get_zone(name)
        +float haversine(lat1, lon1, lat2, lon2)
    }

    class evaluate_zone {
        <<function>>
        +__call__(input, rule_pack, baseline_table, open_event, zone_forecasts, zone_catalog) DecisionOutput
    }

    class project_ratio {
        <<function>>
        +__call__(zone, hour, precip_mm, rule_pack, baseline_table) float
    }

    class classify_risk {
        <<function>>
        +__call__(projected_ratio, precip_mm, rule_pack) RiskLevel|None
    }

    class recommend_earnings {
        <<function>>
        +__call__(current_earnings_mxn, rule_pack) tuple[float, float]
    }

    class rank_secondary_zones {
        <<function>>
        +__call__(zone, zone_forecasts, rule_pack, zone_catalog) list[str]
    }

    evaluate_zone --> DecisionInput : takes
    evaluate_zone --> RulePack : reads
    evaluate_zone --> ZoneCatalog : uses
    evaluate_zone --> DecisionOutput : returns
    evaluate_zone --> project_ratio : calls
    evaluate_zone --> classify_risk : calls
    evaluate_zone --> recommend_earnings : calls
    evaluate_zone --> rank_secondary_zones : calls
    DecisionOutput --> DecisionType
    DecisionOutput --> RiskLevel
```

## Orchestrator → State interaction

```mermaid
classDiagram
    direction TB

    class RunSummary {
        +str run_id
        +str status
        +int zones_evaluated
        +int alerts_emitted
        +str|None error
    }

    class run_cycle {
        <<function>>
        +__call__(settings, rule_pack, zone_catalog, baseline_table, provider, conn) RunSummary
    }

    class repo_runs {
        <<module>>
        +create_run(conn, run_id, city, rule_pack_version)
        +finish_run(conn, run_id, status, zones, alerts, ...)
    }

    class repo_events {
        <<module>>
        +get_open_event(conn, city, zone) dict|None
        +open_event(conn, event_id, city, zone, ...)
        +update_event(conn, event_id, ...)
        +close_event(conn, event_id)
        +increment_dry_streak(conn, event_id) int
        +reset_dry_streak(conn, event_id)
    }

    class repo_decisions {
        <<module>>
        +record_decision(conn, decision_id, run_id, zone, ...)
    }

    class repo_outbox {
        <<module>>
        +enqueue_alert(conn, outbox_id, event_id, city, zone, ...)
        +get_pending_alerts(conn) list[dict]
        +mark_consumed(conn, outbox_id)
    }

    class repo_config {
        <<module>>
        +save_snapshot(conn, snapshot_id, run_id, config_json)
    }

    run_cycle --> RunSummary : returns
    run_cycle --> repo_runs : create / finish run
    run_cycle --> repo_events : open / update / close events
    run_cycle --> repo_decisions : record per-zone decisions
    run_cycle --> repo_outbox : enqueue actionable alerts
    run_cycle --> repo_config : save config snapshot
```

## Table definitions (SQLite)

```mermaid
erDiagram
    pipeline_runs {
        TEXT id PK
        TEXT city
        TEXT rule_pack_version
        TEXT status
        INTEGER zones_evaluated
        INTEGER alerts_emitted
        TEXT started_at
        TEXT finished_at
        TEXT snapshot_id
        TEXT error_message
    }

    alert_events {
        TEXT id PK
        TEXT city
        TEXT zone
        TEXT max_risk
        REAL max_precip_mm
        TEXT opened_at
        TEXT last_sent_at
        TEXT closed_at
        INTEGER dry_streak
        TEXT status
    }

    decision_records {
        TEXT id PK
        TEXT run_id FK
        TEXT zone
        INTEGER forecast_hour
        TEXT forecast_time
        REAL precip_mm
        TEXT decision_type
        TEXT event_id FK
        TEXT risk_level
        REAL projected_ratio
        REAL recommended_earnings_mxn
        REAL uplift_mxn
        INTEGER lead_time_min
        TEXT secondary_zones
        TEXT reason
    }

    alert_outbox {
        TEXT id PK
        TEXT event_id FK
        TEXT city
        TEXT zone
        TEXT forecast_time
        REAL precip_mm
        TEXT risk_level
        REAL projected_ratio
        REAL recommended_earnings_mxn
        REAL uplift_mxn
        INTEGER lead_time_min
        TEXT secondary_zones
        TEXT reason
        TEXT decision_type
        TEXT run_id FK
        TEXT source_snapshot_id
        TEXT rule_pack_version
        TEXT created_at
        TEXT consumed_at
        TEXT status
    }

    effective_config_snapshots {
        TEXT id PK
        TEXT run_id FK
        TEXT config_json
        TEXT created_at
    }

    pipeline_runs ||--o{ decision_records : "run_id"
    pipeline_runs ||--o{ alert_outbox : "run_id"
    pipeline_runs ||--o{ effective_config_snapshots : "run_id"
    alert_events ||--o{ decision_records : "event_id"
    alert_events ||--o{ alert_outbox : "event_id"
```
