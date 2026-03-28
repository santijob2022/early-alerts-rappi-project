# EarlyAlertsAPI

Operational alert backend for Rappi's rain-demand intelligence system.
Fetches precipitation forecasts from Open-Meteo, evaluates zone-level rules, and emits actionable alerts to a SQLite outbox every hour (or every 15 min during peak/elevated periods).

---

## Architecture Overview

Two containers share a single Docker volume (`appdata`) that holds the SQLite and DuckDB files:

| Container | Role |
|---|---|
| `api` | FastAPI + Uvicorn — serves all HTTP endpoints. Scheduler is **OFF**.  |
| `scheduler` | Same image — Uvicorn + APScheduler loop. No public port. |

The scheduler polls at **60-minute intervals** by default, dropping to **15 minutes** when an open alert event exists or the current hour is a peak hour. Both containers write to the same `/data/alerts.db`.

---

## Setup & Running

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (v24+ recommended) with Docker Compose V2.
- Git (to clone the repo).

### 1. Clone the repository

```bash
git clone <repo-url>
cd EarlyAlertsAPI
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

The defaults in `.env.example` work out of the box for local development. Edit only if you need to change the host port or city/timezone:

```
# Host port the API listens on (default: 8000)
API_HOST_PORT=8000

EARLY_ALERTS_CITY=monterrey
EARLY_ALERTS_TIMEZONE=America/Monterrey
```

> **Important:** Do not set `EARLY_ALERTS_ENABLE_SCHEDULER` in `.env`. The `docker-compose.yml` sets it per-service (`false` for `api`, `true` for `scheduler`) to prevent duplicate runs.

### 3. Build the Docker image

```bash
docker compose build
```

This produces the `earlyalertsapi:latest` image used by both services. The build is cached — re-running only re-builds if `pyproject.toml` or `uv.lock` changed.

### 4. Start the stack

```bash
docker compose up -d
```

Expected output:

```
✔ Network earlyalertsapi_default   Created
✔ Volume  earlyalertsapi_appdata   Created
✔ Container earlyalertsapi-api-1       Healthy
✔ Container earlyalertsapi-scheduler-1 Started
```

### 5. Verify the API is up

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:

```json
{"status":"ok","city":"monterrey","open_events":0,"last_run":null}
```

The interactive docs are also available at **http://localhost:8000/docs**.

---

## Common Commands

| Action | Command |
|---|---|
| Start (background) | `docker compose up -d` |
| Stop | `docker compose down` |
| Rebuild after code changes | `docker compose up -d --build` |
| View API logs | `docker logs earlyalertsapi-api-1 -f` |
| View scheduler logs | `docker logs earlyalertsapi-scheduler-1 -f` |
| Trigger a manual run | `curl -X POST http://localhost:8000/api/v1/jobs/run-once` |

---

## API Endpoints

All routes are prefixed with `/api/v1/`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Health check — returns city, open event count, last run timestamp. |
| `GET` | `/api/v1/alerts/latest` | Latest pending alerts from the outbox. |
| `GET` | `/api/v1/events/open` | Currently open alert events. |
| `GET` | `/api/v1/config` | Active configuration (secrets excluded). |
| `POST` | `/api/v1/jobs/run-once` | Trigger one immediate forecast → evaluate → outbox cycle. |

Full interactive docs: **http://localhost:8000/docs**

---

## Scheduler Behaviour

**Yes — once the stack is up, the scheduler runs automatically every hour without any manual intervention.**

- On startup the `scheduler` container registers a recurring APScheduler job with a 60-minute interval.
- The interval self-adjusts to **15 minutes** while any open alert event exists or the current hour is a peak hour.
- If the container restarts (e.g. server reboot), `restart: unless-stopped` in `docker-compose.yml` brings it back automatically.

To trigger a run immediately without waiting, use:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/run-once
```

---

## Data Persistence

The named volume `earlyalertsapi_appdata` is mounted at `/data/` in both containers. It holds:

- `alerts.db` — SQLite database (outbox, events, run history).
- `forecast_warehouse.duckdb` — DuckDB analytical warehouse written by the ingestion layer.

The volume survives `docker compose down`. To fully reset:

```bash
docker compose down -v   # ⚠️ deletes all stored alerts and events
```

### What each cycle writes

Every run — whether triggered by the scheduler or manually via `POST /api/v1/jobs/run-once` — calls the same `run_cycle()` function and writes to both databases.

**SQLite (`alerts.db`)**

| Table | What gets written |
|---|---|
| `pipeline_runs` | One row per cycle — run ID, city, start/end time, status, zones evaluated, alerts emitted |
| `alert_outbox` | One row per alert generated (zone, risk level, precip forecast, recommended earnings) |
| `alert_events` | Open/ongoing alert events per zone (created, updated, or closed) |
| `decision_records` | Raw decision output for every zone evaluated (zone, decision type, risk level, precip) |
| `effective_config_snapshots` | Active config snapshot at time of run |

**DuckDB (`forecast_warehouse.duckdb`)**

| Table | What gets written |
|---|---|
| `forecasts.raw_data` | Raw JSON responses from Open-Meteo, appended |
| `forecasts.normalized_data` | Normalized per-zone hourly precipitation rows, appended |

Both databases use **append-only** writes — nothing is ever overwritten, so every run adds to the full history.

> **Note:** The first run (manual or scheduled) will populate `last_run` in the health endpoint response. Until then, `GET /api/v1/health` returns `"last_run": null`.

To trigger an immediate run and seed the databases without waiting for the scheduler:

```bash
curl -X POST http://localhost:8000/api/v1/jobs/run-once
```

Then verify data was written:

```bash
# Check health endpoint — last_run should now have a timestamp
curl http://localhost:8000/api/v1/health

# Check for any alerts generated
curl http://localhost:8000/api/v1/alerts/latest
```

---

## Alert Thresholds & Rule Pack

Alerts are governed by `app/backend/data/rule_pack_v1.yaml`. Key thresholds:

| Parameter | Value | Meaning |
|---|---|---|
| `triggers.base_mm` | **2.0 mm** | Minimum precipitation to trigger an alert in any zone |
| `triggers.sensitive_peak_mm` | **1.0 mm** | Lower threshold for sensitive zones during peak hours |
| `triggers.critical_escalation_mm` | **5.0 mm** | Escalates alert severity to *crítico* |
| `severity_thresholds.medio_min` | 1.50× | Earnings ratio floor for *medio* |
| `severity_thresholds.alto_min` | 1.80× | Earnings ratio floor for *alto* |
| `severity_thresholds.critico_min` | 2.20× | Earnings ratio floor for *crítico* |

**Peak hours** (local time): 12, 13, 14, 19, 20, 21

**Sensitive zones** (use the lower 1.0 mm threshold during peak hours):
- Santiago, Carretera Nacional, Santa Catarina, MTY_Apodaca_Huinala

**Volume-monitored zones** (watched for demand impacts):
- Centro, San Pedro, MTY_Guadalupe, San Nicolas

> **Why `alerts/latest` may return `[]`:** An empty response is **not a bug** — it simply means the current forecast shows precipitation below the trigger thresholds for all zones. Alerts will appear once any zone's forecast crosses `base_mm` (2.0 mm), or `sensitive_peak_mm` (1.0 mm) for sensitive zones during peak hours.

### Inspect the rule pack

```bash
# Print all top-level keys and trigger thresholds
docker exec earlyalertsapi-api-1 python -c "
import yaml
with open('/app/app/backend/data/rule_pack_v1.yaml') as f:
    rp = yaml.safe_load(f)
print('triggers:', rp['triggers'])
print('peak_hours:', rp['peak_hours'])
print('sensitive_zones:', rp['sensitive_zones'])
"
```

### Inspect SQLite data

```bash
# Run history — how many zones evaluated and alerts emitted per run
docker exec earlyalertsapi-api-1 python -c "
import sqlite3
con = sqlite3.connect('/data/alerts.db')
for row in con.execute('SELECT run_id, started_at, zones_evaluated, alerts_emitted, status FROM pipeline_runs ORDER BY started_at DESC LIMIT 10'):
    print(row)
con.close()
"

# Latest zone decisions — see which zones fired or were suppressed
docker exec earlyalertsapi-api-1 python -c "
import sqlite3
con = sqlite3.connect('/data/alerts.db')
for row in con.execute('SELECT zone, decision, risk_level, precip_mm FROM decision_records ORDER BY created_at DESC LIMIT 30'):
    print(row)
con.close()
"

# Alerts currently in the outbox
docker exec earlyalertsapi-api-1 python -c "
import sqlite3
con = sqlite3.connect('/data/alerts.db')
rows = con.execute('SELECT zone, risk_level, precip_mm, recommended_earnings_mxn, created_at FROM alert_outbox ORDER BY created_at DESC LIMIT 20').fetchall()
print(f'{len(rows)} alert(s) in outbox')
for row in rows:
    print(row)
con.close()
"
```

### Inspect DuckDB forecast warehouse

```bash
# Show available tables
docker exec earlyalertsapi-api-1 python -c "
import duckdb
con = duckdb.connect('//data/forecast_warehouse.duckdb')
print(con.execute('SHOW TABLES').fetchall())
con.close()
"

# Preview the latest normalized forecast rows
docker exec earlyalertsapi-api-1 python -c "
import duckdb
con = duckdb.connect('//data/forecast_warehouse.duckdb')
rows = con.execute('SELECT * FROM forecasts__normalized_data ORDER BY _dlt_load_id DESC LIMIT 10').fetchall()
for r in rows: print(r)
con.close()
"
```

> **Windows / Git Bash note:** Use `//data/...` (double slash) for paths inside `docker exec python -c` commands to prevent Git Bash from translating `/data` to a Windows path.

---

## Development (without Docker)

```bash
# Install uv if not present
pip install uv

# Create venv and install deps
uv sync

# Start API + scheduler in a single process (dev mode)
EARLY_ALERTS_ENABLE_SCHEDULER=true uvicorn app.backend.main:app --reload

# Or trigger one cycle from the CLI
early-alerts run-once
```
