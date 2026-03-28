"""Repository: decision_records table."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Connection, select

from app.backend.state.tables import decision_records


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_decision(
    conn: Connection,
    *,
    decision_id: str,
    run_id: str,
    zone: str,
    forecast_hour: int,
    forecast_time: str,
    precip_mm: float,
    decision_type: str,
    event_id: str | None = None,
    risk_level: str | None = None,
    projected_ratio: float | None = None,
    recommended_earnings_mxn: float | None = None,
    uplift_mxn: float | None = None,
    lead_time_min: int | None = None,
    secondary_zones: list[str] | None = None,
    reason: str | None = None,
) -> None:
    conn.execute(
        decision_records.insert().values(
            id=decision_id,
            run_id=run_id,
            event_id=event_id,
            zone=zone,
            forecast_hour=forecast_hour,
            forecast_time=forecast_time,
            precip_mm=precip_mm,
            decision_type=decision_type,
            risk_level=risk_level,
            projected_ratio=projected_ratio,
            recommended_earnings_mxn=recommended_earnings_mxn,
            uplift_mxn=uplift_mxn,
            lead_time_min=lead_time_min,
            secondary_zones=json.dumps(secondary_zones or []),
            reason=reason,
            created_at=_now_iso(),
        )
    )


def list_decisions_for_run(conn: Connection, run_id: str) -> list[dict]:
    rows = conn.execute(
        select(decision_records).where(decision_records.c.run_id == run_id)
    ).mappings().all()
    return [dict(r) for r in rows]
