"""POST /api/v1/jobs/run-once"""
from __future__ import annotations

import asyncio

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/jobs/run-once", status_code=202)
async def trigger_run_once(request: Request) -> JSONResponse:
    
    """Trigger a single forecast → evaluate → outbox cycle and return summary.

    This administrative endpoint runs the full orchestrator `run_cycle()` once
    using the configured provider, rule pack, zone catalog and baseline table.
    It returns HTTP 202 with a short summary containing `run_id`, `status`,
    and `alerts_emitted`.

    Notes:
    - The call invokes network I/O (provider fetch) and may block while the
        cycle completes; use sparingly and protect with auth in production.
    - The endpoint is intended for manual/operational use (smoke runs,
        debugging, or one-off re-evaluations).
    """
    state = request.app.state
    from app.backend.ingestion.open_meteo import OpenMeteoProvider
    from app.backend.services.orchestrator import run_cycle
    from app.backend.state.database import get_session

    provider = OpenMeteoProvider(
        base_url=state.settings.provider.base_url,
        timeout_seconds=state.settings.provider.timeout_seconds,
        max_retries=state.settings.provider.max_retries,
    )
    with get_session() as conn:
        summary = await run_cycle(
            state.settings,
            state.rule_pack,
            state.zone_catalog,
            state.baseline_table,
            provider,
            conn,
        )
    return JSONResponse(
        status_code=202,
        content={"run_id": summary.run_id, "status": summary.status, "alerts_emitted": summary.alerts_emitted},
    )
