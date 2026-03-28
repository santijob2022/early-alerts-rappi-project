"""SQLAlchemy Core table definitions for operational state.

Uses TEXT for all timestamps (stored as ISO 8601 UTC strings).
Uses TEXT for JSON columns (secondary_zones, config_json).
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Float,
    Table,
    Text,
)

metadata = MetaData()

pipeline_runs = Table(
    "pipeline_runs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("city", Text, nullable=False),
    Column("started_at", Text, nullable=False),
    Column("finished_at", Text),
    Column("status", Text, nullable=False),          # ok / failed / partial
    Column("zones_evaluated", Integer),
    Column("alerts_emitted", Integer),
    Column("snapshot_id", Text),
    Column("rule_pack_ver", Text, nullable=False),
    Column("error_message", Text),
)

alert_events = Table(
    "alert_events",
    metadata,
    Column("id", Text, primary_key=True),
    Column("city", Text, nullable=False),
    Column("zone", Text, nullable=False),
    Column("opened_at", Text, nullable=False),
    Column("closed_at", Text),
    Column("last_sent_at", Text),
    Column("max_risk", Text),
    Column("max_precip_mm", Float),
    Column("status", Text, nullable=False),          # open / closed
    Column("dry_streak", Integer, default=0),
)

decision_records = Table(
    "decision_records",
    metadata,
    Column("id", Text, primary_key=True),
    Column("run_id", Text, nullable=False),
    Column("event_id", Text),
    Column("zone", Text, nullable=False),
    Column("forecast_hour", Integer, nullable=False),
    Column("forecast_time", Text, nullable=False),
    Column("precip_mm", Float, nullable=False),
    Column("decision_type", Text, nullable=False),
    Column("risk_level", Text),
    Column("projected_ratio", Float),
    Column("recommended_earnings_mxn", Float),
    Column("uplift_mxn", Float),
    Column("lead_time_min", Integer),
    Column("secondary_zones", Text),               # JSON array
    Column("reason", Text),
    Column("created_at", Text, nullable=False),
)

alert_outbox = Table(
    "alert_outbox",
    metadata,
    Column("id", Text, primary_key=True),
    Column("event_id", Text, nullable=False),
    Column("city", Text, nullable=False),
    Column("zone", Text, nullable=False),
    Column("forecast_time", Text, nullable=False),
    Column("precip_mm", Float, nullable=False),
    Column("risk_level", Text, nullable=False),
    Column("projected_ratio", Float, nullable=False),
    Column("recommended_earnings_mxn", Float, nullable=False),
    Column("uplift_mxn", Float, nullable=False),
    Column("lead_time_min", Integer, nullable=False),
    Column("secondary_zones", Text, nullable=False),  # JSON array
    Column("reason", Text, nullable=False),
    Column("decision_type", Text, nullable=False),
    Column("status", Text, nullable=False),           # pending / consumed / suppressed
    Column("run_id", Text, nullable=False),
    Column("source_snapshot_id", Text, nullable=False),
    Column("rule_pack_version", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("consumed_at", Text),
)

effective_config_snapshots = Table(
    "effective_config_snapshots",
    metadata,
    Column("id", Text, primary_key=True),
    Column("run_id", Text, nullable=False),
    Column("config_json", Text, nullable=False),
    Column("created_at", Text, nullable=False),
)
