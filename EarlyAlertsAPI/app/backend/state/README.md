State directory: operational persistence for the alerting engine

- Purpose: hold lightweight operational state used by the service (runs, events,
  decisions, outbox, and effective config snapshots).
- DB: SQLite/SQLAlchemy Core is used; `get_engine()` and `get_session()` manage
  connections and transactions.
- Tables: `pipeline_runs`, `alert_events`, `decision_records`, `alert_outbox`,
  `effective_config_snapshots` (see tables.py for schema).
- APIs: repo_* helpers in this folder expose small functions to read/write state
  (create_run, finish_run, open_event, close_event, record_decision, enqueue_alert, etc.).
- Observability: repository calls are intentionally small and synchronous; callers
  may add timing/logging around heavy operations (e.g. snapshot writes) to monitor
  latency.
- Analytics vs runtime state: analytical history (DuckDB via `dlt`) lives outside
  this folder in the ingestion pipeline; this folder is strictly runtime state.
