# EarlyAlertsAPI — Technical Documentation

> **Module 2c · Weather-Driven Alert Outbox for Dynamic Pricing**  
> Version 0.1.0 · Python 3.13 · FastAPI · SQLite + DuckDB

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
   - 2.1 [High-level data flow](#21-high-level-data-flow)
   - 2.2 [Module boundary](#22-module-boundary)
   - 2.3 [Storage split rationale](#23-storage-split-rationale)
   - 2.4 [Runtime modes](#24-runtime-modes)
3. [Directory Layout](#3-directory-layout)
4. [Configuration](#4-configuration)
   - 4.1 [config.yaml](#41-configyaml)
   - 4.2 [rule_pack_v1.yaml](#42-rule_pack_v1yaml)
   - 4.3 [monterrey_zones.yaml](#43-monterrey_zonesyaml)
   - 4.4 [baseline_ratios.yaml](#44-baseline_ratiosyaml)
   - 4.5 [Environment variable overrides](#45-environment-variable-overrides)
5. [Calibrated Constants](#5-calibrated-constants)
6. [Decision Engine](#6-decision-engine)
   - 6.1 [Rain projection (projections.py)](#61-rain-projection-projectionspy)
   - 6.2 [Risk classification (severity.py)](#62-risk-classification-severitypy)
   - 6.3 [Earnings recommendation (earnings.py)](#63-earnings-recommendation-earningspy)
   - 6.4 [Secondary zone ranking (secondary_zones.py)](#64-secondary-zone-ranking-secondary_zonespy)
   - 6.5 [Main engine (engine.py)](#65-main-engine-enginepy)
7. [Ingestion Layer](#7-ingestion-layer)
   - 7.1 [Open-Meteo adapter](#71-open-meteo-adapter)
   - 7.2 [Normalizer](#72-normalizer)
   - 7.3 [dlt pipeline (DuckDB)](#73-dlt-pipeline-duckdb)
8. [State Layer (SQLite)](#8-state-layer-sqlite)
   - 8.1 [Table definitions](#81-table-definitions)
   - 8.2 [Repositories](#82-repositories)
9. [Orchestrator & Memory Logic](#9-orchestrator--memory-logic)
   - 9.1 [Cycle steps](#91-cycle-steps)
   - 9.2 [Cooldown & suppression](#92-cooldown--suppression)
   - 9.3 [Escalation criteria](#93-escalation-criteria)
   - 9.4 [Dry-close streak](#94-dry-close-streak)
10. [REST API](#10-rest-api)
11. [CLI Commands](#11-cli-commands)
12. [Scheduler](#12-scheduler)
13. [Testing Strategy](#13-testing-strategy)
    - 13.1 [Mandatory scenarios](#131-mandatory-scenarios)
    - 13.2 [Running tests](#132-running-tests)
14. [Module 3 Handoff Contract](#14-module-3-handoff-contract)
15. [Development Workflow](#15-development-workflow)
    - 15.1 [Local setup (no Docker)](#151-local-setup-no-docker)
    - 15.2 [Docker / Production deployment](#152-docker--production-deployment)
16. [Non-Goals for v1](#16-non-goals-for-v1)

---

## 1  Overview

`EarlyAlertsAPI` is the backend component in the Rappi AI Engineer case study. It implements a weather-driven alert engine optimised for the Monterrey (MX) food-delivery market.

**Business problem**: During rain events, demand for food delivery surges. Earners (drivers) on the platform should be proactively notified to increase their availability and adjust their expected earnings before rain starts. Notifying too early is noise; notifying too late misses revenue.

**Solution**: The service polls Open-Meteo hourly forecasts for 14 Monterrey zones, runs a calibrated decision engine against historical baseline ratios, and writes structured alerts to an outbox table. Module 3 (LLM + Telegram) consumes the outbox without any knowledge of the weather logic.

**Key properties**:
- **Zero magic numbers** – all calibrated constants live in `EarlyAlertsAPI\app\backend\core\rule_pack.pyl`.
- **Pure decision engine** – `evaluate_zone()` in `EarlyAlertsAPI\app\backend\decision\engine.py` is a pure function; no I/O.
- **Radon CC ≤ B** on every function.
- **Richardson Maturity Level 2** REST API.
- **31/31 unit tests pass** covering all 8 mandatory scenarios from the spec.

---

## 2  Architecture

### 2.1  High-level data flow

```
┌──────────────────────────────────────────────────────────────┐
│                         Scheduler                             │
│   (adaptive: 60 min default / 15 min elevated)               │
└──────────────────────────┬───────────────────────────────────┘
                           │ triggers
                           ▼
┌─────────────────── Orchestrator ──────────────────────────────┐
│  1. create_run (SQLite)                                        │
│  2. save config snapshot (SQLite)                             │
│  3. fetch_hourly_forecast (Open-Meteo, 1 HTTP call / 14 zones)│
│  4. run_pipeline  ──►  DuckDB (raw + normalized rows)         │
│  5. build zone_forecasts dict for t+1                         │
│  6. for each zone:                                            │
│       evaluate_zone (pure) → DecisionOutput                   │
│       memory logic → open/update/close event (SQLite)         │
│       enqueue_alert if actionable (SQLite)                    │
│  7. watchlist scan t+2, t+3 (WATCH records only)             │
│  8. finish_run (SQLite)                                       │
└──────────────────────────────────────────────────────────────┘
          │
          ▼
   alert_outbox (SQLite)
          │
          ▼  (Module 3 boundary)
   LLM prose generation → Telegram send → mark_consumed
```

### 2.2  Module boundary

The service **ends** at the `alert_outbox` table. The outbox record is the formal contract:

- A subsequent service polls `repo_outbox.get_pending_alerts()`.
- It calls an LLM with the structured data to generate Telegram prose.
- After sending, it calls `repo_outbox.mark_consumed(id)`.
- Such a subseuent module should **not** re-fetch weather data or re-run decision logic.

### 2.3  Storage split rationale

| Store | Responsibility | Technology |
|---|---|---|
| **DuckDB** (via `dlt`) | Raw forecast snapshots, normalised `zone_forecast` rows, ingestion lineage | Append-only analytical history |
| **SQLite** (via SQLAlchemy Core) | `pipeline_runs`, `alert_events`, `decision_records`, `alert_outbox`, `effective_config_snapshots` | Low-latency transactional application state |

`dlt` owns ingestion history. SQLite owns application state. They are independent failure domains.

### 2.4  Runtime modes

| Mode | Entry | Use case |
|---|---|---|
| `run-once` | `early-alerts run-once` | Single cycle, print results. Demo & debug. |
| `serve` | `early-alerts serve` | FastAPI + APScheduler. Module 3 integration (single-process). |
| `list-open-events` | `early-alerts list-open-events` | Inspect open events in SQLite. |
| API only | `uvicorn app.backend.main:app` | API workers without scheduler (production default). |
| Docker | `docker compose up --build` | Recommended production: `api` + `scheduler` containers. |

**Scheduler toggle** — `EARLY_ALERTS_ENABLE_SCHEDULER` (default `false`) controls whether a process starts APScheduler. In Docker the `scheduler` service sets it to `true`; all `api` workers leave it `false`. This prevents duplicate orchestrator runs.

---

## 3  Directory Layout

```
app/backend/
├── main.py                    ← FastAPI app factory + lifespan
├── cli.py                     ← Typer CLI
├── api/
│   ├── router.py              ← APIRouter aggregator
│   ├── health.py              ← GET /health
│   ├── config_routes.py       ← GET /config
│   ├── alerts.py              ← GET /alerts/latest
│   ├── events.py              ← GET /events/open
│   └── jobs.py                ← POST /jobs/run-once
├── core/
│   ├── config.py              ← Pydantic Settings (YAML + env)
│   ├── models.py              ← Frozen Pydantic domain models
│   ├── constants.py           ← Enums (RiskLevel, DecisionType, …)
│   ├── rule_pack.py           ← RulePack loader
│   └── zone_catalog.py        ← ZoneCatalog loader + Haversine
├── ingestion/
│   ├── provider_base.py       ← ForecastProvider ABC
│   ├── open_meteo.py          ← OpenMeteoProvider (batch + fallback)
│   ├── normalizer.py          ← raw → ZoneForecastRow list
│   └── pipeline.py            ← dlt pipeline → DuckDB
├── decision/
│   ├── engine.py              ← evaluate_zone() pure function
│   ├── severity.py            ← classify_risk()
│   ├── earnings.py            ← recommend_earnings()
│   ├── secondary_zones.py     ← rank_secondary_zones()
│   └── projections.py         ← project_ratio() + bucketize_rain()
├── state/
│   ├── database.py            ← SQLite engine + get_session()
│   ├── tables.py              ← SQLAlchemy Core table definitions
│   ├── repo_runs.py           ← pipeline_runs CRUD
│   ├── repo_events.py         ← alert_events CRUD
│   ├── repo_decisions.py      ← decision_records CRUD
│   ├── repo_outbox.py         ← alert_outbox CRUD
│   └── repo_config.py         ← effective_config_snapshots CRUD
├── services/
│   ├── orchestrator.py        ← run_cycle() — single cycle
│   └── scheduler.py           ← APScheduler with adaptive interval
├── data/
│   ├── config.yaml            ← Default runtime configuration
│   ├── rule_pack_v1.yaml      ← All calibrated thresholds
│   ├── monterrey_zones.yaml   ← 14 zone centroids + metadata
│   └── baseline_ratios.yaml   ← Precomputed dry-condition ratios
├── scripts/
│   └── generate_baseline_table.py   ← One-time parquet → YAML
└── tests/
    ├── conftest.py
    ├── test_decision_engine.py
    ├── test_ingestion.py
    ├── test_memory.py
    ├── test_orchestrator.py
    └── test_api.py
```

---

## 4  Configuration

All configuration starts from `app/backend/data/config.yaml` and can be overridden with `EARLY_ALERTS_*` environment variables (double-underscore for nested keys).

### 4.1  `config.yaml`

```yaml
version: 1
city: "monterrey"
timezone: "America/Monterrey"

provider:
  name: "open_meteo"
  base_url: "https://api.open-meteo.com/v1/forecast"
  timeout_seconds: 30
  max_retries: 2

polling:
  default_interval_minutes: 60
  elevated_interval_minutes: 15

storage:
  sqlite_path: "data/alerts.db"
  duckdb_path: "data/forecast_warehouse.duckdb"

rule_pack_file: "rule_pack_v1.yaml"
zone_catalog_file: "monterrey_zones.yaml"

module3:
  outbox_enabled: true
```

### 4.2  `rule_pack_v1.yaml`

Single source of truth for **all calibrated constants**. No magic numbers exist anywhere in production code.

Key sections:

| Section | Purpose |
|---|---|
| `triggers` | Base trigger 2.0 mm/hr; sensitive+peak override 1.0 mm/hr; critical escalation 5.0 mm/hr |
| `peak_hours` | `[12, 13, 14, 19, 20, 21]` (local time) |
| `sensitive_zones` | 4 zones with separate peak trigger and floor ratio |
| `volume_monitors` | 4 zones ranked high in secondary suggestions |
| `rain_buckets` | Dry/light/moderate/heavy precipitation boundaries |
| `rain_lifts` | Ratio lift values by period (peak/offpeak) × bucket |
| `sensitive_peak_floors` | Per-zone floor ratio applied when `1.0 ≤ precip < 2.0` at peak |
| `severity_thresholds` | 1.50 (medio) / 1.80 (alto) / 2.20 (critico) |
| `earnings` | Target 80 MXN; baseline 55.6 MXN |
| `memory` | Cooldown 4h; dry-close streak 2h; delta thresholds for re-send |
| `secondary_zones` | Max 2; fallback neighbours per primary zone |
| `horizons` | Primary 60 min; watchlist max 180 min |

### 4.3  `monterrey_zones.yaml`

14 zones with WGS-84 centroids and description text. This file is the **runtime source**; the backend never touches parquet at runtime.

### 4.4  `baseline_ratios.yaml`

Pre-computed from `DataAnalysis/outputs/cleaned/raw_data_clean.parquet`. Run once:

```bash
DataAnalysis/.venv/Scripts/python.exe app/backend/scripts/generate_baseline_table.py
```

Three lookup levels:

```yaml
by_zone_hour:          # primary lookup: zone × local hour
  Santiago:
    13: 1.8412
    ...
by_zone_period:        # fallback 1: zone × (peak | offpeak)
  Santiago:
    peak: 1.6543
    offpeak: 0.4120
by_zone:               # fallback 2: zone average
  Santiago: 0.8760
```

### 4.5  Environment variable overrides

All runtime configuration keys declared in `app/backend/core/config.py` can be overridden with environment variables prefixed by `EARLY_ALERTS_`. Nested keys use a double-underscore `__` as the delimiter (this is configured in `Settings.model_config`). The app loads `app/backend/data/config.yaml` first and then applies environment overrides when `get_settings()` is called.

Commonly used overrides (name → `Settings` field → default):

- `EARLY_ALERTS_CITY` → `city` → `monterrey`
- `EARLY_ALERTS_TIMEZONE` → `timezone` → `America/Monterrey`
- `EARLY_ALERTS_PROVIDER__NAME` → `provider.name` → `open_meteo`
- `EARLY_ALERTS_PROVIDER__BASE_URL` → `provider.base_url` → `https://api.open-meteo.com/v1/forecast`
- `EARLY_ALERTS_PROVIDER__TIMEOUT_SECONDS` → `provider.timeout_seconds` → `30`
- `EARLY_ALERTS_PROVIDER__MAX_RETRIES` → `provider.max_retries` → `2`
- `EARLY_ALERTS_POLLING__DEFAULT_INTERVAL_MINUTES` → `polling.default_interval_minutes` → `60`
- `EARLY_ALERTS_POLLING__ELEVATED_INTERVAL_MINUTES` → `polling.elevated_interval_minutes` → `15`
- `EARLY_ALERTS_STORAGE__SQLITE_PATH` → `storage.sqlite_path` → `data/alerts.db`
- `EARLY_ALERTS_STORAGE__DUCKDB_PATH` → `storage.duckdb_path` → `data/forecast_warehouse.duckdb`
- `EARLY_ALERTS_RULE_PACK_FILE` → `rule_pack_file` → `rule_pack_v1.yaml`
- `EARLY_ALERTS_ZONE_CATALOG_FILE` → `zone_catalog_file` → `monterrey_zones.yaml`
- `EARLY_ALERTS_MODULE3__OUTBOX_ENABLED` → `module3.outbox_enabled` → `true`
- `EARLY_ALERTS_EARNINGS_BASELINE_MXN` → `earnings_baseline_mxn` → `55.6`
- `EARLY_ALERTS_ENABLE_SCHEDULER` → `enable_scheduler` → `false` (set `true` only for the dedicated scheduler container)

Examples (from `.env.example`):

```bash
# Point to a test database
EARLY_ALERTS_STORAGE__SQLITE_PATH=/tmp/test.db
EARLY_ALERTS_STORAGE__DUCKDB_PATH=/tmp/test.duckdb

# Disable Module 3 outbox during development
EARLY_ALERTS_MODULE3__OUTBOX_ENABLED=false
```

See `app/backend/core/config.py` for the full `Settings` model and defaults. Use `.env` in development or set environment variables at the container/service level (as in `docker-compose.yml`) for production.

---

## 5  Calibrated Constants

All values derived from analytics in `DataAnalysis/notebooks/03_kpis_and_findings.ipynb`.

| Constant | Value | Evidence |
|---|---|---|
| Base trigger | 2.0 mm/hr at t+1 | [M1-P2][CALC-1] |
| Sensitive-zone peak override | 1.0 mm/hr at t+1 | [M1-P3][CALC-1] |
| Primary alert horizon | 1 h | [CALC-1] |
| Watchlist horizon | 3 h (silent) | [CALC-1] |
| Target earnings | 80 MXN | [M1-P5][CALC-1] |
| Cooldown window | 4 h per zone-event | [CALC-1] |
| Dry-close condition | 2 consecutive dry hours | [CALC-1] |
| Peak hours | {12, 13, 14, 19, 20, 21} | [M1-P1] |
| Sensitive zones | Santiago, Carretera Nacional, Santa Catarina, MTY_Apodaca_Huinalá | [M1-P3] |
| Volume monitors | Centro, San Pedro, MTY_Guadalupe, San Nicolás | [M1-P3] |

---

## 6  Decision Engine

All decision logic is **pure**: `evaluate_zone()` takes inputs and returns a `DecisionOutput` with no side effects.

### 6.1  Rain projection (`projections.py`)

```python
project_ratio(zone, forecast_hour, precip_mm, rule_pack, baseline_table) → float
```

1. Looks up `baseline_no_rain_ratio` via fallback chain:
   `by_zone_hour[zone][hour]` → `by_zone_period[zone][peak|offpeak]` → `by_zone[zone]` → city-wide mean.
2. Selects rain lift from rule pack (peak vs offpeak × bucket).
3. Applies **sensitive-peak floor** override: when the zone is sensitive, hour is peak, and `1.0 ≤ precip < 2.0`, the projected ratio is raised to at least the zone's calibrated floor (e.g., Santiago = 2.700).

### 6.2  Risk classification (`severity.py`)

```python
classify_risk(projected_ratio, precip_mm, rule_pack) → RiskLevel | None
```

| Condition | Result |
|---|---|
| `ratio < 1.50` | `None` (not actionable) |
| `1.50 ≤ ratio < 1.80` | `MEDIO` |
| `1.80 ≤ ratio < 2.20` | `ALTO` |
| `ratio ≥ 2.20` | `CRITICO` |
| `precip ≥ 5.0` **and** risk ≥ ALTO | Force `CRITICO` (heavy-rain override) |

### 6.3  Earnings recommendation (`earnings.py`)

```python
recommend_earnings(current_earnings_mxn, rule_pack) → (recommended, uplift)
```

- If `current < 80.0` → return `(80.0, 80.0 - current)`.
- Otherwise → return `(current, 0.0)`.

### 6.4  Secondary zone ranking (`secondary_zones.py`)

```python
rank_secondary_zones(primary_zone, zone_forecasts, rule_pack, zone_catalog) → list[str]
```

Algorithm:
1. Filter zones with `precip_mm ≥ 1.0` at t+1 (excluding primary zone).
2. Sort: **sensitive zones first → volume monitors → rest**.
3. Tiebreak by `precip_mm` descending.
4. Final tiebreak by Haversine distance from primary zone ascending.
5. If no candidates, use `fallback_neighbors[primary_zone]` from the rule pack.
6. Return at most 2.

### 6.5  Main engine (`engine.py`)

Decision tree for `evaluate_zone()`:

```
1. lead_time_min = max((forecast_hour - current_hour) % 24 * 60, 60)
2. if lead_time_min > 60 → WATCH / SUPPRESS (watchlist horizon)
3. if precip_mm < 0.1   → SUPPRESS (dry)
4. project ratio + classify risk
5. if precip_mm < trigger_mm → WATCH
6. if risk == MEDIO and NOT (peak AND sensitive) → WATCH
7. if risk is None → SUPPRESS
8. compute earnings + rank secondary zones → ALERT
```

`evaluate_zone` has Radon CC = 8 (grade A).

---

## 7  Ingestion Layer

### 7.1  Open-Meteo adapter

`OpenMeteoProvider` sends a **single HTTP call** with comma-separated `latitude,longitude` params for all 14 centroids. Falls back to bounded concurrent requests (`asyncio.Semaphore(4)`) if the batch endpoint fails.

```python
provider.fetch_hourly_forecast(coordinates, hours_ahead=6) → list[dict]
```

Retries up to `max_retries` (default 2) with 1-second delays. Raises `httpx.HTTPError` on exhaustion. The orchestrator catches this and marks the run as failed without corrupting open events.

### 7.2  Normalizer

`normalize(raw_responses, coordinates, catalog, run_id, fetched_at) → list[ZoneForecastRow]`

- Matches each coordinate back to its zone via centroid lookup (tolerance 0.001°).
- Converts UTC timestamps to `America/Monterrey` local time.
- Produces one `ZoneForecastRow` per `zone × forecast_hour`.
- Clamps precipitation to `≥ 0.0`.

### 7.3  dlt pipeline (DuckDB)

Two append-only resources:

| Resource | Grain |
|---|---|
| `raw_forecast_snapshots` | One row per HTTP response (JSON as string), timestamped with `run_id` |
| `normalized_zone_forecasts` | One row per `zone × forecast_hour` (14 zones × 6 hours = 84 rows/cycle) |

The DuckDB file can be used for offline replay, trend analysis, and ingestion lineage audits without touching SQLite.

---

## 8  State Layer (SQLite)

### 8.1  Table definitions

**`pipeline_runs`** — one row per scheduled cycle.

| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | UUID |
| city | TEXT | "monterrey" |
| started_at / finished_at | TEXT | ISO 8601 UTC |
| status | TEXT | "running" \| "ok" \| "failed" \| "partial" |
| zones_evaluated | INTEGER | |
| alerts_emitted | INTEGER | |
| snapshot_id | TEXT | links to DuckDB run_id |
| rule_pack_ver | TEXT | |
| error_message | TEXT | populated on failure |

**`alert_events`** — tracks the lifecycle of a rain event per zone.

| Column | Notes |
|---|---|
| id | UUID |
| status | "open" \| "closed" |
| max_risk | highest risk seen during event |
| max_precip_mm | highest precip seen |
| dry_streak | consecutive dry t+1 observations since last wet |
| last_sent_at | used for cooldown calculation |

**`decision_records`** — one row per zone per cycle (every outcome, including WATCH/SUPPRESS).

**`alert_outbox`** — structured records for Module 3 consumption.

| Column | Notes |
|---|---|
| status | "pending" \| "consumed" \| "suppressed" |
| consumed_at | set by Module 3 |
| risk_level, projected_ratio, recommended_earnings_mxn | core payload |
| secondary_zones | JSON array |
| rule_pack_version | traceability |

**`effective_config_snapshots`** — full resolved config JSON saved at start of every run.

### 8.2  Repositories

Each `repo_*.py` exposes plain functions (not classes). One function per operation. No hidden state.

```python
# Examples
repo_events.get_open_event(conn, city, zone) → dict | None
repo_events.open_event(conn, ...)
repo_events.increment_dry_streak(conn, event_id) → int  # returns new streak
repo_outbox.enqueue_alert(conn, ...)
repo_outbox.get_pending_alerts(conn, limit=100) → list[dict]
repo_outbox.mark_consumed(conn, outbox_id)
```

---

## 9  Orchestrator & Memory Logic

### 9.1  Cycle steps

```
run_cycle(settings, rule_pack, zone_catalog, baseline_table, provider, conn)
```

1. `create_run` in SQLite.
2. `save_snapshot` of resolved config.
3. `fetch_hourly_forecast` → if fails, mark run "failed", return early.
4. `run_pipeline` → DuckDB (non-fatal on failure).
5. Build `zone_t1` dict: `{zone → ZoneForecastRow}` for `current_hour + 1`.
6. For each of 14 zones: engine.evaluate_zone → memory logic → write state.
7. Watchlist scan for t+2, t+3 (WATCH records only, no outbox).
8. `finish_run` with counts.

### 9.2  Cooldown & suppression

After the first alert for a zone:
- A new alert is **suppressed** for 4 hours unless escalation criteria are met.
- Outside the 4-hour window, the alert is re-sent and `last_sent_at` is updated.

`_should_suppress(open_event, decision_output, rule_pack) → bool`

### 9.3  Escalation criteria

During cooldown, suppression is bypassed if **any** of:
- `decision_output.risk_level > open_event.max_risk`
- `current_precip - open_event.max_precip_mm ≥ 1.0 mm`
- `recommended_earnings - previous_recommended ≥ 5.0 MXN`

When bypassed under cooldown, `decision_type` is upgraded to `ESCALATE`.

### 9.4  Dry-close streak

After each dry (precip < 0.1 mm) cycle for an open event:
1. `dry_streak` is incremented.
2. If `dry_streak ≥ 2`, the event is closed.
3. A WATCH or ALERT resets `dry_streak` to 0.

---

## 10  REST API

Base path: `/api/v1`

| Method | Path | Status | Description |
|---|---|---|---|
| `GET` | `/health` | 200 | Service status: city, open_events count, last_run timestamp |
| `GET` | `/config` | 200 | Full resolved settings JSON |
| `POST` | `/jobs/run-once` | 202 | Trigger a single synchronous forecast cycle |
| `GET` | `/alerts/latest` | 200 | Recent outbox records; query params: `?limit=20&status=pending` |
| `GET` | `/events/open` | 200 | All currently open alert events |

Error responses follow RFC 7807:

```json
{
  "type": "about:blank",
  "title": "Provider Unavailable",
  "status": 502,
  "detail": "Open-Meteo returned 503"
}
```

### Example: `GET /api/v1/health`

```json
{
  "status": "ok",
  "city": "monterrey",
  "open_events": 2,
  "last_run": "2026-03-25T18:00:12.345678+00:00"
}
```

### Example: `POST /api/v1/jobs/run-once` (202 Accepted)

```json
{
  "run_id": "3e4f5a6b-...",
  "status": "ok",
  "alerts_emitted": 3
}
```

---

## 11  CLI Commands

All commands load settings from `app/backend/data/config.yaml` (overridable via env vars).

### `early-alerts run-once`

Runs one full cycle and prints structured alerts to stdout:

```
──────────────────────────────────────────────────────
ALERT | Santiago | Risk: CRITICO
  Precipitación esperada: 6.8 mm/hr en las próximas 1h
  Ratio proyectado: ~2.70 (basado en histórico)
  Acción: subir earnings de 55.6 a 80.0 MXN (+24.4)
  Zonas secundarias: Carretera Nacional, MTY_Guadalupe
──────────────────────────────────────────────────────
```

If no alerts:
```
── No alerts generated ──
Zones evaluated: 14
```

### `early-alerts serve`

Starts `uvicorn` on `0.0.0.0:8000` with APScheduler running in the background.

### `early-alerts list-open-events`

Prints a table of all open alert events from SQLite.

---

## 12  Scheduler

`services/scheduler.py` wraps APScheduler `BackgroundScheduler`.

**Adaptive interval logic** — after each cycle, the next interval is chosen:

| Condition | Interval |
|---|---|
| ≥ 1 open event in SQLite **OR** current hour in `{12,13,14,19,20,21}` | 15 min (elevated) |
| Otherwise | 60 min (default) |

On provider failure: logs error, marks run "failed", does **not** close or mutate open events.

---

## 13  Testing Strategy

### 13.1  Mandatory scenarios

All 8 mandatory test scenarios from the technical spec pass:

| # | Input | Expected | Test |
|---|---|---|---|
| 1 | Santiago, 13h, 1.2 mm/hr, earnings 70 | ALERT, risk ≥ ALTO, ratio ≥ 2.70, rec 80 MXN | `test_s1_santiago_peak_sensitive_triggers_alert` |
| 2 | Centro, 13h, 1.2 mm/hr | WATCH (below base trigger) | `test_s2_centro_below_base_trigger_is_watch` |
| 3 | Centro, 14h, 2.5 mm/hr | ALERT, ALTO | `test_s3_centro_moderate_rain_peak_alto` |
| 4 | Any zone, t+3 = 3.0 mm/hr, lead 180 min | WATCH (no outbox) | `test_s4_watchlist_horizon_t3_is_watch` |
| 5 | Same storm, 3 polls | 1 alert + 2 suppress | `test_s5_cooldown_suppresses_duplicates` |
| 6 | 2 dry hours after open event | Event closes | `test_s6_dry_streak_closes_event` |
| 7 | Active event + risk escalates | ESCALATE + new outbox | `test_s7_escalation_bypasses_cooldown` |
| 8 | Provider failure mid-cycle | Run fails, events intact | `test_s8_provider_failure_does_not_corrupt_events` |

Test suite breakdown:

| File | Tests | Coverage |
|---|---|---|
| `test_decision_engine.py` | 14 | Pure engine, bucketize, severity, earnings (scenarios 1–4) |
| `test_memory.py` | 3 | Cooldown, dry-close, escalation (scenarios 5–7) |
| `test_orchestrator.py` | 3 | Full cycle, provider failure, decision records (scenario 8) |
| `test_ingestion.py` | 5 | Normalizer, coord matching, null precip, FakeProvider |
| `test_api.py` | 5 | All 5 REST endpoints, including POST /jobs/run-once with mock |

**Total: 31 tests, 31 pass.**

### 13.2  Running tests

```bash
# From EarlyAlertsAPI/ root
.venv/Scripts/python.exe -m pytest app/backend/tests/ -v --tb=short

# Run only engine tests
.venv/Scripts/python.exe -m pytest app/backend/tests/test_decision_engine.py -v
```

Code quality checks:
```bash
# Lint
.venv/Scripts/ruff check app/backend/ --fix

# Complexity (fail on any C or worse)
.venv/Scripts/radon cc app/backend/ -a --min C

# Maintainability index
.venv/Scripts/radon mi app/backend/ --min B
```

---

## 14  Module 3 Handoff Contract

Module 3 reads from `alert_outbox` via `repo_outbox.get_pending_alerts()`.

Each outbox row contains everything needed to generate a Telegram message:

| Field | Module 3 use |
|---|---|
| `zone` + `risk_level` | Message header |
| `precip_mm` + `lead_time_min` | "What to expect" section |
| `projected_ratio` | Historical context footnote |
| `recommended_earnings_mxn` + `uplift_mxn` | Specific action line |
| `secondary_zones` | "Also monitor" list |
| `reason` | LLM system context |
| `rule_pack_version` | Traceability / audit |

After sending, Module 3 calls `repo_outbox.mark_consumed(outbox_id)`.

---

## 15  Development Workflow

### 15.1  Local setup (no Docker)

```bash
# 1. Install all dependencies
uv sync

# 2. Generate baseline ratios (one-time, requires DataAnalysis venv)
../DataAnalysis/.venv/Scripts/python.exe app/backend/scripts/generate_baseline_table.py

# 3. Run a single demo cycle
early-alerts run-once
# or:
.venv/Scripts/python.exe -m app.backend.cli run-once

# 4. Start the API server (scheduler enabled in same process)
early-alerts serve
# or via Uvicorn directly (no scheduler by default):
.venv/Scripts/uvicorn app.backend.main:app --reload
```

> **Note:** `early-alerts serve` starts the scheduler because the CLI entry point
> always enables it. `uvicorn app.backend.main:app` will only start the scheduler
> if `EARLY_ALERTS_ENABLE_SCHEDULER=true` is set.

---

### 15.2  Docker / Production deployment

#### Prerequisites

- Docker ≥ 24 and Docker Compose v2 (`docker compose`)
- The `data/` directory on the **host** (or a named volume) for SQLite + DuckDB persistence

#### Quick start

```bash
# 1. Copy the environment template and review it
cp .env.example .env

# 2. Build the image and start both services
docker compose up --build
```

This starts two containers from a single image:

| Container | Role | Scheduler |
|---|---|---|
| `earlyalertsapi-api-1` | FastAPI + 2 uvicorn workers, port 8000 | OFF (`EARLY_ALERTS_ENABLE_SCHEDULER=false`) |
| `earlyalertsapi-scheduler-1` | Single APScheduler loop, no external traffic | ON (`EARLY_ALERTS_ENABLE_SCHEDULER=true`) |

Both containers share the same `/data` named volume so SQLite and DuckDB are
shared state.

#### Useful commands

```bash
# Start in the background
docker compose up --build -d

# View live logs
docker compose logs -f api
docker compose logs -f scheduler

# Stop everything
docker compose down

# Stop and delete the data volume (full reset)
docker compose down -v

# Scale API replicas (scheduler always stays at 1)
docker compose up --scale api=3 -d
```

#### Health check

Docker polls `GET http://localhost:8000/api/v1/health` every 30 s.
The `scheduler` container waits for `api` to report healthy before starting
(configured via `depends_on: condition: service_healthy`).

```bash
# Manual check
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{"status": "ok", "city": "monterrey", "open_events": 0, "last_run": null}
```

#### Environment variables

All runtime knobs are in `.env` (gitignored). See `.env.example` for the full
reference. The most important ones:

| Variable | Default | Notes |
|---|---|---|
| `EARLY_ALERTS_ENABLE_SCHEDULER` | `false` | Set to `true` only in the scheduler container (done automatically by docker-compose.yml) |
| `EARLY_ALERTS_STORAGE__SQLITE_PATH` | `/data/alerts.db` | Override to use a custom path or external mount |
| `EARLY_ALERTS_STORAGE__DUCKDB_PATH` | `/data/forecast_warehouse.duckdb` | Same |
| `API_HOST_PORT` | `8000` | Host port the API binds to |
| `EARLY_ALERTS_MODULE3__OUTBOX_ENABLED` | `true` | Disable to run in dry-run / no-outbox mode |

#### Persistence

```
# Named volume location (Linux)
/var/lib/docker/volumes/earlyalertsapi_appdata/_data/

# Named volume location (Windows — Docker Desktop)
\\wsl.localhost\docker-desktop-data\data\docker\volumes\...
```

Back up the volume before upgrades:

```bash
docker run --rm \
  -v earlyalertsapi_appdata:/data \
  -v $(pwd)/backup:/backup \
  alpine tar czf /backup/appdata_$(date +%F).tar.gz /data
```

#### Production hardening checklist

- [ ] Put Nginx (or cloud ALB) in front of port 8000 for TLS termination
- [ ] Add `X-Forwarded-For` / `X-Forwarded-Proto` headers at the reverse proxy
- [ ] Set `--workers 4` (or more) in the `api` service `CMD` to match CPU count
- [ ] Replace SQLite with Postgres for multi-replica API deployments
- [ ] Mount `appdata` volume on persistent network storage (EBS, GCE PD, etc.)
- [ ] Configure log shipping (CloudWatch, Datadog, etc.) from container stdout
- [ ] Set up a liveness probe and alerting on `pipeline_runs` where `status = failed`

---

### Database inspection

```bash
# SQLite
sqlite3 data/alerts.db ".tables"
sqlite3 data/alerts.db "SELECT * FROM alert_outbox ORDER BY created_at DESC LIMIT 5;"

# DuckDB (Python)
.venv/Scripts/python.exe -c "
import duckdb
con = duckdb.connect('data/forecast_warehouse.duckdb')
print(con.execute('SHOW TABLES').fetchall())
"
```

### Adding a new weather provider

1. Create `ingestion/my_provider.py` implementing `ForecastProvider`.
2. Return raw JSON preserving `hourly.time` and `hourly.precipitation` shape.
3. Set `EARLY_ALERTS_PROVIDER__NAME=my_provider` and instantiate in `cli.py`.
4. Zero changes needed to the decision engine.

### Porting to a second city

1. Add a new `data/<city>_zones.yaml` with zone centroids.
2. Run `generate_baseline_table.py` filtered to that city.
3. Set `EARLY_ALERTS_CITY=<city>`, `EARLY_ALERTS_ZONE_CATALOG_FILE=<city>_zones.yaml`.
4. SQLite tables are keyed by `city`, so both cities can share the same DB.

---

## 16  Non-Goals for v1

- LLM-generated message text
- Telegram delivery
- Config write API
- Polygon/grid multi-point spatial aggregation
- Multi-city deployment
- Cloud infrastructure (AWS, GCP, etc.)
- Frontend / UI
- Authentication on API endpoints

---

## 17  Querying the Databases

Both databases live in the `appdata` Docker volume, mounted at `/data/` inside every container.

### 17.1  SQLite (`alerts.db`) — browser UI

A `sqlite-web` container is included in `docker-compose.yml` and exposes a full browser interface.

**Step 1 — Start the services** (if not already running):

```bash
cd EarlyAlertsAPI
docker compose up -d
```

**Step 2 — Open the browser UI:**

```
http://localhost:8080
```

The left sidebar lists all tables. Click any table to browse rows, or use the **Query** tab to run arbitrary SQL.

**Useful queries:**

```sql
-- All alerts, newest first
SELECT * FROM alerts ORDER BY created_at DESC;

-- Only unconsumed (pending) alerts
SELECT * FROM alerts WHERE consumed_at IS NULL ORDER BY created_at DESC;

-- Alerts by risk level
SELECT risk_level, COUNT(*) AS total FROM alerts GROUP BY risk_level;

-- Alerts from the last 24 hours
SELECT * FROM alerts
WHERE created_at >= datetime('now', '-1 day')
ORDER BY created_at DESC;
```

> **Port override**: set `SQLITE_WEB_PORT=<port>` in `.env` if 8080 is already in use.

---

### 17.2  DuckDB (`forecast_warehouse.duckdb`) — via docker exec

DuckDB has no dedicated browser UI in this stack. Use `docker exec` to drop into a Python session inside the running API container, where `duckdb` is already installed.

**Step 1 — Open an interactive Python shell:**

```bash
docker exec -it earlyalertsapi-api-1 python
```

**Step 2 — Connect and explore:**

```python
import duckdb
con = duckdb.connect("/data/forecast_warehouse.duckdb")

# List all schemas
con.execute("SELECT schema_name FROM information_schema.schemata").df()

# List all tables (dlt writes to the 'forecasts' schema)
con.execute("SELECT table_schema, table_name FROM information_schema.tables").df()
```

**Step 3 — Run queries:**

```python
# Row counts
con.execute("SELECT COUNT(*) FROM forecasts.normalized_zone_forecasts").df()

# Latest forecast rows (all zones)
con.execute("SELECT * FROM forecasts.normalized_zone_forecasts ORDER BY forecast_time DESC LIMIT 20").df()

# Hourly precipitation for a specific zone
con.execute("""
    SELECT forecast_time, zone, precip_mm
    FROM forecasts.normalized_zone_forecasts
    WHERE zone = 'Centro'
    ORDER BY forecast_time DESC
    LIMIT 48
""").df()

# Precipitation summary by zone for the latest run
con.execute("""
    SELECT zone,
           ROUND(SUM(precip_mm), 2)  AS total_mm,
           ROUND(MAX(precip_mm), 2)  AS peak_mm
    FROM forecasts.normalized_zone_forecasts
    WHERE run_id = (SELECT MAX(run_id) FROM forecasts.normalized_zone_forecasts)
    GROUP BY zone
    ORDER BY total_mm DESC
""").df()

con.close()
```

**One-liner (no interactive shell):**

```bash
docker exec earlyalertsapi-api-1 python -c \
  "import duckdb; print(duckdb.connect('/data/forecast_warehouse.duckdb').execute('SELECT table_schema, table_name FROM information_schema.tables').df())"
```

---

### 17.3  Connecting from the host (advanced)

If you prefer a local DuckDB client or Jupyter notebook, copy the database file out of the volume first:

```bash
# Find the volume mount path on the host
docker inspect earlyalertsapi-api-1 --format '{{ range .Mounts }}{{ .Source }}{{ end }}'

# Or copy to your working directory
docker cp earlyalertsapi-api-1:/data/forecast_warehouse.duckdb ./forecast_warehouse.duckdb
docker cp earlyalertsapi-api-1:/data/alerts.db ./alerts.db
```

Then open them locally with any SQLite browser (e.g. [DB Browser for SQLite](https://sqlitebrowser.org/)) or a DuckDB client.
