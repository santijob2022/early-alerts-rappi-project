"""GET /api/v1/events/open"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/events/open")
async def open_events(request: Request) -> list[dict]:
    """List currently open alert events for the configured city.

    Uses `request.app.state.settings.city` to scope results to the service's
    configured city. Returns a list of event dictionaries containing the
    runtime state for each open event (ids, risk, max_precip, timestamps,
    etc.).

    Typical use: admin dashboards, monitoring, and human review tools.
    Consider restricting or authenticating this endpoint in production.
    """
    from app.backend.state.database import get_session
    from app.backend.state import repo_events
    with get_session() as conn:
        return repo_events.list_open_events(conn, request.app.state.settings.city)
