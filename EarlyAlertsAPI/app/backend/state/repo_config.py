"""Repository: effective_config_snapshots table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Connection, select

from app.backend.state.tables import effective_config_snapshots


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_snapshot(conn: Connection, snapshot_id: str, run_id: str, config_json: str) -> None:
    conn.execute(
        effective_config_snapshots.insert().values(
            id=snapshot_id,
            run_id=run_id,
            config_json=config_json,
            created_at=_now_iso(),
        )
    )


def get_latest_snapshot(conn: Connection) -> dict | None:
    row = conn.execute(
        select(effective_config_snapshots)
        .order_by(effective_config_snapshots.c.created_at.desc())
        .limit(1)
    ).mappings().first()
    return dict(row) if row else None
