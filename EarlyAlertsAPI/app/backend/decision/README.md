Decision module
=================

Responsibilities
----------------
- Contain the pure decision logic that maps forecast context into a `DecisionOutput`.
- Keep business rules deterministic and side-effect free so the orchestrator can call the engine safely.
- Provide a single public entrypoint used by the orchestrator to evaluate a zone at a given horizon.

Public functions
----------------
- `evaluate_zone(input, rule_pack, baseline_table, open_event, zone_forecasts, zone_catalog)`
  - Inputs: a `DecisionInput` describing the zone/horizon/forecast, a `RulePack` (business rules),
    the `baseline_table` used for ratio projection, any current `open_event` for memory/cooldown logic,
    `zone_forecasts` (map of zone→precip for neighbor ranking), and the `ZoneCatalog`.
  - Returns: a `DecisionOutput` (one of ALERT / WATCH / SUPPRESS / ESCALATE) with recommended earnings,
    uplift, lead time, ranked secondary zones, and a human-readable `reason`.
  - Characteristics: pure function, no I/O, no DB or network access. All side effects (opening/closing events,
    queuing alerts, recording decisions) are performed by the orchestrator.

Internal helpers
----------------
- `_compute_lead_time(forecast_hour, current_hour)` — compute lead time in minutes (min 60).
- `_build_suppress(reason)` / `_build_watch(reason, lead_time_min)` — small helpers that construct `DecisionOutput` instances.

High-level evaluation flow
--------------------------
1. Compute lead time and determine whether the horizon is a watchlist horizon (t+2/t+3) or actionable t+1.
2. For watchlist horizons (lead > 60 min): return WATCH if forecast ≥ trigger; otherwise SUPPRESS.
3. For t+1: if forecast is below `dry_threshold_mm` → SUPPRESS (dry close logic lives in orchestrator).
4. Project the ratio using historical `baseline_table` and classify risk via `classify_risk()`.
5. If precip < configured trigger → WATCH.
6. If risk is MEDIO but not in sensitive+peak → WATCH (non-actionable MEDIO).
7. If no actionable risk → SUPPRESS.
8. Otherwise compute recommended earnings (`recommend_earnings`) and rank secondary zones (`rank_secondary_zones`)
   then return an ALERT/ESCALATE `DecisionOutput`.

Concurrency and invocation
--------------------------
- The engine is intentionally pure and thread-safe: `evaluate_zone()` has no side effects and can be called
  concurrently by multiple workers or threads.
- In the current codebase the orchestrator calls `evaluate_zone()` sequentially in a loop (see
  [app/backend/services/orchestrator.py](app/backend/services/orchestrator.py)), handling memory, cooldowns,
  DB writes, and the outbox itself. That means there is no internal parallelism across zones today.
- If you need faster evaluation for many zones, you can parallelize at the orchestrator level (map/reduce style,
  worker pool, or asyncio tasks) because the engine itself is safe to run concurrently. When doing so:
  - Keep memory / state writes single-threaded or use transactional DB updates to avoid races.
  - Preserve ordering for the cooldown/update logic if you move to a concurrent model.

Tests and examples
------------------
- See `app/backend/tests/test_decision_engine.py` for unit-level examples of calling `evaluate_zone()`.

Files
-----
- Engine implementation: [app/backend/decision/engine.py](app/backend/decision/engine.py)
