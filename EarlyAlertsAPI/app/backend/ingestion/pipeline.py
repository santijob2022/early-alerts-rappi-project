"""dlt pipeline: land raw + normalized zone forecasts into DuckDB.

Two resources with append-only write disposition preserve full history.
Returns a snapshot_id for orchestrator lineage tracking.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

import dlt

from app.backend.core.models import ZoneForecastRow

logger = logging.getLogger(__name__)


def _raw_resource(
    raw_responses: list[dict],
    run_id: str,
    fetched_at: datetime,
) -> Iterator[dict]:
    for i, payload in enumerate(raw_responses):
        yield {
            "run_id": run_id,
            "coord_index": i,
            "fetched_at": fetched_at.isoformat(),
            "payload": str(payload),  # store as string; analytical replay via DuckDB JSON funcs
        }


def _normalized_resource(rows: list[ZoneForecastRow]) -> Iterator[dict]:
    for row in rows:
        yield {
            "run_id": row.run_id,
            "zone": row.zone,
            "forecast_hour": row.forecast_hour,
            "forecast_time": row.forecast_time.isoformat(),
            "precip_mm": row.precip_mm,
            "fetched_at": row.fetched_at.isoformat(),
        }


def run_pipeline(
    raw_responses: list[dict],
    normalized_rows: list[ZoneForecastRow],
    run_id: str,
    duckdb_path: str,
) -> str:
    """Ingest raw + normalized data into DuckDB.

    Returns the snapshot_id (= run_id) for orchestrator lineage.
    """
    fetched_at = datetime.now(timezone.utc)

    pipeline = dlt.pipeline(
        pipeline_name="early_alerts_forecast",
        destination=dlt.destinations.duckdb(credentials=duckdb_path),
        dataset_name="forecasts",
    )

    raw_res = dlt.resource(
        list(_raw_resource(raw_responses, run_id, fetched_at)),
        name="raw_forecast_snapshots",
        write_disposition="append",
    )
    norm_res = dlt.resource(
        list(_normalized_resource(normalized_rows)),
        name="normalized_zone_forecasts",
        write_disposition="append",
    )

    try:
        pipeline.run([raw_res, norm_res])
        logger.info("dlt pipeline succeeded for run_id=%s", run_id)
    except Exception as exc:
        logger.error("dlt pipeline failed for run_id=%s: %s", run_id, exc)
        raise

    return run_id
