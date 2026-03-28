Orchestrator and Scheduler — Services Overview
=============================================

This directory contains the lightweight runtime services that drive periodic alert cycles: the scheduler that triggers cycles and the orchestrator that performs a full fetch→decide→persist cycle.

Key responsibilities
--------------------
- Scheduler (`start_scheduler`) — schedule and reschedule periodic cycles using APScheduler.
  - Decides whether to use the default or elevated polling interval based on peak hours (from the rule pack) or presence of open alert events in the state DB.
  - Runs a wrapper job which invokes the orchestrator once per interval and then reschedules the next run according to current conditions.

- Orchestrator (`run_cycle`) — execute a single alert cycle. High-level steps:
  1. Create a run record and snapshot current settings (operational DB).
  2. Fetch forecasts from the configured provider (single batched API call for all zone centroids).
  3. Normalize provider responses into `ZoneForecastRow` objects.
  4. Schedule asynchronous analytical persistence (DuckDB via `dlt.pipeline`) in a background thread.
  5. Build the t+1 map and sequentially evaluate each zone by calling the pure decision engine.
  6. Apply memory logic (cooldown, dry_streak, open/close events) and record decisions, events, and outbox messages to the operational DB.
  7. Record watchlist decisions for t+2/t+3 horizons.
  8. Finish the run and write summary counts.

How decisions are taken
-----------------------
- Decision logic is implemented in the pure function `evaluate_zone()` (see `app/backend/decision/engine.py`). It:
  - Accepts a `DecisionInput` (zone, forecast hour, precip, current earnings), a `RulePack`, the `baseline_table`, optional `open_event`, a `zone_forecasts` map (for neighbor ranking), and the `ZoneCatalog`.
  - Returns a `DecisionOutput` describing one of: `ALERT`, `ESCALATE`, `WATCH`, or `SUPPRESS`, with metadata (risk level, projected ratio, recommended earnings, uplift, lead time, secondary zones, reason).

- The orchestrator is responsible for all side effects and stateful behavior:
  - It reads/writes `alert_events`, `decision_records`, `outbox`, and `pipeline_runs` using repository helpers under `app/backend/state`.
  - It enforces memory/cooldown rules (when to suppress, escalate or close events) using `repo_events` helpers.
  - It sets optimistic `snapshot_id` for analytical persistence but does not block on the DuckDB write.

Concurrency model
-----------------
- The engine (`evaluate_zone`) is pure and thread-safe; it may be run concurrently if you parallelize at the orchestrator level.
- Current implementation: orchestrator evaluates zones sequentially in a loop and performs DB writes synchronously inside the same transaction (via `get_session()`). This avoids race conditions at the cost of throughput.
- The DuckDB/dlt pipeline is launched asynchronously (background thread) to reduce blocking of orchestrator runtime.

Extending or parallelizing
--------------------------
- If you need more throughput for many zones:
  - Run `evaluate_zone()` concurrently (ThreadPoolExecutor, asyncio tasks with `asyncio.to_thread`) but funnel DB writes through a single writer or use transactional/locking semantics to avoid races.
  - Alternatively split evaluation and state persistence into two stages: workers compute `DecisionOutput` objects and send them into a single writer queue (or lightweight worker) that serializes DB mutations.

Operational notes
-----------------
- The scheduler runs jobs in background threads (`BackgroundScheduler`) and calls `asyncio.run(run_cycle(...))` inside the job wrapper. Each scheduled job runs to completion in its own thread.
- `_reschedule()` updates the job trigger for future runs only — it does not interrupt the currently running job. It computes interval choices after the run completes (so decisions use DB state at reschedule time).
- If you modify the rule-pack YAML or other static data, a process restart is required to pick up import-time loads; consider reading `application.state` dynamically if you need runtime reloads.

Testing and observability
-------------------------
- Unit tests: `app/backend/tests/test_decision_engine.py` demonstrates calling the pure engine with sample inputs.
- Logs: orchestrator emits info/warning logs for snapshot durations, provider failures, background pipeline completion/failure, and run summaries.
- Metrics: consider adding counters for background pipeline failures, alerts emitted, and average cycle duration.

Files of interest
-----------------
- `app/backend/services/scheduler.py` — scheduler start/reschedule logic.
- `app/backend/services/orchestrator.py` — full cycle implementation and memory logic.
- `app/backend/decision/engine.py` — pure decision logic.
- `app/backend/state/*` — repository helpers for operational state (events, decisions, outbox, runs).

Next steps you might want
------------------------
- Add a writer-queue pattern if you parallelize evaluation.
- Add lifecycle hooks to await outstanding background persistence tasks on shutdown.
- Expose lightweight metrics for background pipeline successes/failures and alerts counts.
