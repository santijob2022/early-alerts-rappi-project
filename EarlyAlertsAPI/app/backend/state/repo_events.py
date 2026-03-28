"""Repository: alert_events table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Connection, and_, select

from app.backend.state.tables import alert_events


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_open_event(conn: Connection, city: str, zone: str) -> dict | None:
    row = conn.execute(
        select(alert_events).where(
            and_(
                alert_events.c.city == city,
                alert_events.c.zone == zone,
                alert_events.c.status == "open",
            )
        )
    ).mappings().first()
    return dict(row) if row else None


def open_event(
    conn: Connection,
    event_id: str,
    city: str,
    zone: str,
    max_risk: str,
    max_precip_mm: float,
) -> None:
    now = _now_iso()
    conn.execute(
        alert_events.insert().values(
            id=event_id,
            city=city,
            zone=zone,
            opened_at=now,
            last_sent_at=now,
            max_risk=max_risk,
            max_precip_mm=max_precip_mm,
            status="open",
            dry_streak=0,
        )
    )


def update_event(
    conn: Connection,
    event_id: str,
    max_risk: str | None = None,
    max_precip_mm: float | None = None,
) -> None:
    values: dict = {"last_sent_at": _now_iso()}
    if max_risk is not None:
        values["max_risk"] = max_risk
    if max_precip_mm is not None:
        values["max_precip_mm"] = max_precip_mm
    conn.execute(
        alert_events.update().where(alert_events.c.id == event_id).values(**values)
    )


def close_event(conn: Connection, event_id: str) -> None:
    conn.execute(
        alert_events.update()
        .where(alert_events.c.id == event_id)
        .values(status="closed", closed_at=_now_iso())
    )


def increment_dry_streak(conn: Connection, event_id: str) -> int:
    """Increment dry_streak counter and return the new value."""
    row = conn.execute(
        select(alert_events.c.dry_streak).where(alert_events.c.id == event_id)
    ).scalar()
    new_streak = (row or 0) + 1
    conn.execute(
        alert_events.update()
        .where(alert_events.c.id == event_id)
        .values(dry_streak=new_streak)
    )
    return new_streak


def reset_dry_streak(conn: Connection, event_id: str) -> None:
    conn.execute(
        alert_events.update()
        .where(alert_events.c.id == event_id)
        .values(dry_streak=0)
    )


def list_open_events(conn: Connection, city: str) -> list[dict]:
    rows = conn.execute(
        select(alert_events).where(
            and_(alert_events.c.city == city, alert_events.c.status == "open")
        )
    ).mappings().all()
    return [dict(r) for r in rows]


def count_open_events(conn: Connection, city: str) -> int:
    rows = conn.execute(
        select(alert_events).where(
            and_(alert_events.c.city == city, alert_events.c.status == "open")
        )
    ).fetchall()
    return len(rows)
