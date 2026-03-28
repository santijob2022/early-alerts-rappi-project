"""Alert outbox endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


@router.patch("/alerts/{alert_id}/consume")
async def consume_alert(alert_id: str) -> dict:
    """Mark an alert as consumed by an external consumer (e.g. TelegramAIAgent).

    This is purely additive — it calls the same mark_consumed() used internally
    by the scheduler. No existing logic is affected.
    """
    from sqlalchemy import select
    from app.backend.state.database import get_session
    from app.backend.state import repo_outbox
    from app.backend.state.tables import alert_outbox as _tbl
    with get_session() as conn:
        row = conn.execute(
            select(_tbl).where(_tbl.c.id == alert_id)
        ).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id!r} not found")
        repo_outbox.mark_consumed(conn, alert_id)
    return {"status": "consumed", "id": alert_id}


@router.get("/alerts/latest")
async def latest_alerts(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> list[dict]:
    """Return recent alert records from the outbox.

    Query parameters:
    - `limit` (int): maximum number of alerts to return (1-100).
    - `status` (str|None): optional status filter (for example `sent`,
      `pending`, `failed`).

    Returns a list of alert dictionaries as stored in the outbox. The
    `secondary_zones` column (if stored as JSON text) is parsed into a list
    before returning.

    Intended consumers: admin UIs, debugging tools, or manual inspection of
    recent alerts. This endpoint reads directly from the operational state
    database and is not rate-limited.
    """
    from app.backend.state.database import get_session
    from app.backend.state import repo_outbox
    with get_session() as conn:
        rows = repo_outbox.get_latest_alerts(conn, limit=limit, status=status)
    for row in rows:
        if isinstance(row.get("secondary_zones"), str):
            row["secondary_zones"] = json.loads(row["secondary_zones"])
    return rows
