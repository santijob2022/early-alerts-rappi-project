"""GET /api/v1/health"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    """Return service health and basic runtime information.

    Performs lightweight checks against the runtime state and the local
    operational database to report:
    - `status`: service health string ("ok")
    - `city`: configured city from settings
    - `open_events`: number of currently open alert events
    - `last_run`: ISO timestamp of the most recent orchestrator run or None

    This endpoint is intended for internal monitoring and debugging. Avoid
    exposing it publicly without authentication.
    """

    state = request.app.state
    open_events: int = 0
    last_run: str | None = None
    try:
        from app.backend.state.database import get_session
        from app.backend.state import repo_events, repo_runs
        with get_session() as conn:
            open_events = repo_events.count_open_events(conn, state.settings.city)
            latest = repo_runs.get_latest_run(conn, state.settings.city)
            last_run = latest["started_at"] if latest else None
    except Exception:
        pass
    return {"status": "ok", "city": state.settings.city, "open_events": open_events, "last_run": last_run}
