(**Provenance & regeneration**)

- Canonical analysis artifacts live in the `DataAnalysis` project (parquet files under `DataAnalysis/outputs/cleaned/`). Notebooks such as `notebooks/01_alert_rules_motor_calibration.ipynb` (a.k.a. CALC-1) use those parquets to derive numeric constants.
- Runtime artifacts used by the backend are compact YAML files (for example `app/backend/data/monterrey_zones.yaml` and `app/backend/data/rule_pack_v1.yaml`). These YAMLs are intentionally small, human-editable, and cheap to load at runtime.
- Best practice: treat the parquet outputs as the canonical source of truth for analyses, and generate runtime YAMLs from them with a short reproducible script or notebook cell. When generating YAMLs, include metadata fields such as `version`, `generated_at`, `source_notebook`, and `source_checksum` so we can trace numbers back to the exact notebook and parquet used.
- Suggested regen command (example):

```
python scripts/regenerate_runtime_artifacts.py \
	--input DataAnalysis/outputs/cleaned/zone_info_clean.parquet \
	--notebook notebooks/01_alert_rules_motor_calibration.ipynb \
	--output app/backend/data/monterrey_zones.yaml
```

- If you want, I can extract the exact notebook cell(s) that computed the values used in `rule_pack_v1.yaml` and either embed them here or turn the extraction into a small regeneration script.

**Baseline generation & CI**

- Baseline generator: `app/backend/scripts/generate_baseline_table.py` reads `DataAnalysis/outputs/cleaned/raw_data_clean.parquet` and writes `app/backend/data/baseline_ratios.yaml` (used at runtime by the decision engine).
- How it was run: the script is intended to be executed from the repository root using the Python from the `DataAnalysis` virtualenv (example in the script docstring). The repo does not currently embed run timestamps into the YAML; provenance is therefore not stored in the generated artifact.
- Recommended improvements (short-term):
	- Add provenance metadata to the generated YAML (`generated_at`, `source_parquet`, `generator`, `git_commit`) so each run is traceable.
	- Add CLI flags to the script (`--output`, `--force`, `--source`) to make CI invocation explicit and idempotent.
	- Add a small unit or smoke check in CI that verifies the generated YAML has expected keys and non-empty zones.

- Deployment recommendations (options):
	1. CI regeneration (recommended): run the script in CI after `DataAnalysis` artifacts update, validate the outputs, then commit or publish the YAML artifact. Docker images remain small and runtime deterministic.
	2. Build-time regeneration: run the generator during `docker build` if you can make the parquet available to the build context (not recommended for large parquets or frequent data changes).
	3. Runtime regeneration: run the script at container start if fresh parquets are mounted — acceptable only if startup latency and resource usage are acceptable.

- Example minimal provenance snippet to add to the script before dumping YAML:

```py
import datetime, subprocess
payload['_meta'] = {
		'generated_at': datetime.datetime.utcnow().isoformat() + 'Z',
		'source_parquet': str(PARQUET_PATH),
		'generator': 'generate_baseline_table.py',
		'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip(),
}
```

- I can implement these small changes now (add metadata and CLI flags) and update the script, or scaffold a CI job snippet (GitHub Actions) that runs the generator and commits/publishes the artifact. Which do you prefer?

**Precompute distances (performance improvement)**

- Problem: `rank_secondary_zones()` computes Haversine distances at runtime for each candidate zone, which repeats calculations and can be unnecessary overhead when the zone catalog is static.
- Suggestion: precompute a neighbor-distance map (or K-nearest list) at catalog load time and store it in `app/backend/data/` (or embed in the `monterrey_zones.yaml`) so `rank_secondary_zones()` can look up distances instead of recalculating them.
- Benefits: lower CPU and latency at decision time, deterministic neighbor lists, and easier testing. Trade-off: small extra storage and a short generation step when the catalog changes.
- Implementation options:
	- Precompute and store `neighbors_by_zone.yaml` with sorted neighbor lists and distances. Load into `ZoneCatalog` at startup.
	- Compute a KNN map in `ZoneCatalog` on first use and cache it in-memory (lazily). Use `distance_km()` once per pair.
	- Add a one-off script `scripts/precompute_neighbors.py` to regenerate the neighbor map when zones change.

- I can add a small `scripts/precompute_neighbors.py` and wire `ZoneCatalog` to optionally load a precomputed neighbor map — want me to add that now?

**dlt pipeline non-blocking / timing**

- Problem: the `dlt` ingestion pipeline is executed synchronously inside `run_cycle()` which can increase scheduler and API-triggered run latency.
- Suggested short-term improvements:
	- Add timing logs around `run_pipeline()` to measure current impact (`start/end duration`).
	- Make `dlt` ingestion non-blocking by running `run_pipeline()` in a background thread/task (e.g. `asyncio.to_thread` + `asyncio.create_task`) so the orchestrator doesn't wait for DuckDB writes.
	- For stronger isolation, move ingestion to a separate worker (Celery/RQ) and push normalized payloads to a queue.

I can add the timing logs and a non-blocking `asyncio.to_thread` wrapper as a small patch; want me to apply that change now?

**Shutdown / graceful termination (recommended improvements)**

- Problem: on process shutdown the scheduler currently calls `shutdown(wait=False)` which does not wait
	for in-flight jobs to finish and may leave a `run_cycle()` mid-flight or background persistence (dlt) unfinished.
- Short-term change (minimal): set `shutdown(wait=True)` in the FastAPI lifespan cleanup so the process waits
	for the currently running scheduled job to complete before exiting. This ensures the last `run_cycle()` has
	a chance to finish its synchronous DB writes and to record a final run status.

	- Update in `app/backend/main.py` lifespan cleanup:

```py
scheduler_instance = getattr(application.state, "scheduler", None)
if scheduler_instance and scheduler_instance.running:
		scheduler_instance.shutdown(wait=True)
```

- Run completion guarantees: ensure `run_cycle()` always records a final `repo_runs.finish_run(...)` on any
	unexpected exception. Add a top-level try/except/finally around the orchestration so a `run_id` is never left
	without a terminal status (ok/failed). This makes post-mortem and retries deterministic.

- Background persistence durability: the dlt/DuckDB write is currently scheduled from inside the orchestrator
	using `asyncio.to_thread(...)` and is not awaited on shutdown. Options:
	1. Short-term: run the pipeline in a dedicated daemon `threading.Thread` and join it with timeout on shutdown.
	2. Recommended: push analytical persistence to an external worker/queue (Celery, RQ, or a lightweight worker)
		 so the scheduler process is not responsible for guaranteeing long-running writes.
	3. Long-term: switch to an `AsyncIOScheduler` and track `asyncio.Task` objects in application state to await
		 them during shutdown.

- Operational suggestions:
	- Add a small completion/health column to `pipeline_runs` so the background ingestion can mark success/failure.
	- Add a metric/counter for background pipeline failures so we can alert if persistence fails during shutdown.
	- Consider `max_instances=1` and `coalesce=True` when adding the APScheduler job to avoid overlapping runs.

I can apply the `shutdown(wait=True)` change and add a top-level `run_cycle()` guard plus a short note to the
orchestrator to record failures; say "yes" and I'll patch these files.  

**Restart / persistence behaviour**

- Observation: operational state (open events, recorded decisions, outbox rows, and run summaries) is persisted in the application's SQLite database and is reloaded/queried on startup. The app initializes the DB in [app/backend/main.py](app/backend/main.py) and other modules read/write these tables via the `repo_*` helpers.
- What to expect on restart: previously created open events, decisions, outbox entries and run records remain available after a restart and the API/orchestrator will continue operating against that persisted state.
- Important caveats:
	- If the process is terminated while a cycle is running, that run may be left without a terminal `finish_run` status. The repo currently relies on `repo_runs.finish_run(...)` being called at the end of `run_cycle()`, so interrupted runs may appear incomplete.
	- Analytical persistence using `dlt`/DuckDB is launched as a background task from the orchestrator; abrupt shutdown may interrupt that background work and cause analytical writes to be lost unless persistence is made durable or awaited during shutdown.
	- The scheduler is currently shut down with `wait=False` in the lifespan cleanup, which can terminate running jobs immediately on shutdown.
- Recommended immediate changes (I can apply these):
	- Change the lifespan shutdown to `scheduler.shutdown(wait=True)` so the process waits for any running scheduled job to finish.
	- Add a top-level try/except/finally in `run_cycle()` to ensure `repo_runs.finish_run(...)` is always called (marking the run failed on exceptions).
	- Track background ingestion tasks (or move persistence to a durable worker) so analytical writes are not lost on restart; minimally, record pipeline-run status in the DB so failures are visible.

If you'd like, I can apply the three immediate changes now: `shutdown(wait=True)`, `run_cycle()` finish-run guard, and a small pipeline-run status marker. Which should I implement first?

**Scheduler / compose operational notes**

- Important operational notes:
	- Only enable the scheduler in one container (`EARLY_ALERTS_ENABLE_SCHEDULER: "true"`) — your compose file already does that.
	- If `api` later becomes unhealthy or restarts, Compose will try to restart it but will not automatically stop/restart `scheduler` because `depends_on` is start-time only.
	- The `scheduler` container runs `early-alerts serve`, which starts a local FastAPI instance plus the APScheduler loop — the internal HTTP server is for optional health checks only.
	- If you want stricter coupling (e.g., stop scheduler if api fails), I can propose changes (health-based restart policies or a small supervisor script). Which would you prefer?

