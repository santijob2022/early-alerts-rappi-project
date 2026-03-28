"""Repository: alert_outbox table."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Connection, select

from app.backend.state.tables import alert_outbox


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue_alert(
    conn: Connection,
    *,
    outbox_id: str,
    event_id: str,
    city: str,
    zone: str,
    forecast_time: str,
    precip_mm: float,
    risk_level: str,
    projected_ratio: float,
    recommended_earnings_mxn: float,
    uplift_mxn: float,
    lead_time_min: int,
    secondary_zones: list[str],
    reason: str,
    decision_type: str,
    run_id: str,
    source_snapshot_id: str,
    rule_pack_version: str,
) -> None:
    conn.execute(
        alert_outbox.insert().values(
            id=outbox_id,
            event_id=event_id,
            city=city,
            zone=zone,
            forecast_time=forecast_time,
            precip_mm=precip_mm,
            risk_level=risk_level,
            projected_ratio=projected_ratio,
            recommended_earnings_mxn=recommended_earnings_mxn,
            uplift_mxn=uplift_mxn,
            lead_time_min=lead_time_min,
            secondary_zones=json.dumps(secondary_zones),
            reason=reason,
            decision_type=decision_type,
            status="pending",
            run_id=run_id,
            source_snapshot_id=source_snapshot_id,
            rule_pack_version=rule_pack_version,
            created_at=_now_iso(),
        )
    )


def get_pending_alerts(conn: Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        select(alert_outbox)
        .where(alert_outbox.c.status == "pending")
        .order_by(alert_outbox.c.created_at.asc())
        .limit(limit)
    ).mappings().all()
    return [dict(r) for r in rows]


def get_latest_alerts(conn: Connection, limit: int = 20, status: str | None = None) -> list[dict]:
    query = select(alert_outbox).order_by(alert_outbox.c.created_at.desc()).limit(limit)
    if status:
        query = query.where(alert_outbox.c.status == status)
    rows = conn.execute(query).mappings().all()
    return [dict(r) for r in rows]


def mark_consumed(conn: Connection, outbox_id: str) -> None:
    conn.execute(
        alert_outbox.update()
        .where(alert_outbox.c.id == outbox_id)
        .values(status="consumed", consumed_at=_now_iso())
    )


def mark_suppressed(conn: Connection, outbox_id: str) -> None:
    conn.execute(
        alert_outbox.update()
        .where(alert_outbox.c.id == outbox_id)
        .values(status="suppressed")
    )
