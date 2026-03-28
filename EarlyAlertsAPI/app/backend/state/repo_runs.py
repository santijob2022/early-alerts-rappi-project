"""Repository: pipeline_runs table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Connection, select

from app.backend.state.tables import pipeline_runs


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run(conn: Connection, run_id: str, city: str, rule_pack_ver: str) -> None:
    conn.execute(
        pipeline_runs.insert().values(
            id=run_id,
            city=city,
            started_at=_now_iso(),
            status="running",
            rule_pack_ver=rule_pack_ver,
        )
    )


def finish_run(
    conn: Connection,
    run_id: str,
    status: str,
    zones_evaluated: int,
    alerts_emitted: int,
    snapshot_id: str | None = None,
    error_message: str | None = None,
) -> None:
    conn.execute(
        pipeline_runs.update()
        .where(pipeline_runs.c.id == run_id)
        .values(
            finished_at=_now_iso(),
            status=status,
            zones_evaluated=zones_evaluated,
            alerts_emitted=alerts_emitted,
            snapshot_id=snapshot_id,
            error_message=error_message,
        )
    )


def get_run(conn: Connection, run_id: str) -> dict | None:
    row = conn.execute(
        select(pipeline_runs).where(pipeline_runs.c.id == run_id)
    ).mappings().first()
    return dict(row) if row else None


def get_latest_run(conn: Connection, city: str) -> dict | None:
    row = conn.execute(
        select(pipeline_runs)
        .where(pipeline_runs.c.city == city)
        .order_by(pipeline_runs.c.started_at.desc())
        .limit(1)
    ).mappings().first()
    return dict(row) if row else None
