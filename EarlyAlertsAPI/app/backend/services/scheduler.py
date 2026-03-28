"""APScheduler background loop with adaptive interval logic.

Adaptive interval:
- Default: 60 min
- Elevated (15 min) if any open event exists OR current hour is peak.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import yaml
from apscheduler.schedulers.background import BackgroundScheduler

from app.backend.core.config import get_settings
from app.backend.core.rule_pack import load_rule_pack
from app.backend.core.zone_catalog import load_zone_catalog

logger = logging.getLogger(__name__)

# Load peak hours from canonical rule pack YAML; if unavailable mark as not present.
try:
    _RULE_PACK = load_rule_pack(get_settings().rule_pack_path)
    _PEAK_HOURS = set(_RULE_PACK.peak_hours)
except Exception as exc:
    logger.warning("Could not load peak hours from rule pack: %s", exc)
    _PEAK_HOURS = None


def _is_elevated(app_state) -> bool:
    """Return True if polling interval should be elevated (15 min)."""
    current_hour = datetime.now().hour
    if _PEAK_HOURS is not None and current_hour in _PEAK_HOURS:
        return True
    try:
        from app.backend.state.database import get_session
        from app.backend.state import repo_events
        with get_session() as conn:
            return repo_events.count_open_events(conn, app_state.settings.city) > 0
    except Exception as exc:
        logger.warning("open events check failed: %s", exc)
        return False


def _run_cycle_sync(application) -> None:
    """Synchronous wrapper called by APScheduler."""
    from app.backend.ingestion.open_meteo import OpenMeteoProvider
    from app.backend.services.orchestrator import run_cycle
    from app.backend.state.database import get_session

    state = application.state
    provider = OpenMeteoProvider(
        base_url=state.settings.provider.base_url,
        timeout_seconds=state.settings.provider.timeout_seconds,
        max_retries=state.settings.provider.max_retries,
    )
    try:
        with get_session() as conn:
            summary = asyncio.run(run_cycle(
                state.settings, state.rule_pack, state.zone_catalog,
                state.baseline_table, provider, conn,
            ))
        logger.info("Scheduled cycle done: %s alerts emitted", summary.alerts_emitted)
    except Exception as exc:
        logger.error("Scheduled cycle failed: %s", exc)


def _reschedule(scheduler: BackgroundScheduler, application, job_id: str = "cycle") -> None:
    """Reschedule the cycle job based on current conditions."""
    elevated = _is_elevated(application.state)
    interval_min = application.state.settings.polling.elevated_interval_minutes if elevated else \
        application.state.settings.polling.default_interval_minutes

    job = scheduler.get_job(job_id)
    if job:
        scheduler.reschedule_job(job_id, trigger="interval", minutes=interval_min)
    logger.debug("Next cycle in %d min (elevated=%s)", interval_min, elevated)


def start_scheduler(application) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    interval_min = application.state.settings.polling.default_interval_minutes

    def _wrapped():
        _run_cycle_sync(application)
        _reschedule(scheduler, application)

    scheduler.add_job(_wrapped, "interval", minutes=interval_min, id="cycle", misfire_grace_time=60)
    scheduler.start()
    logger.info("Scheduler started (interval=%d min)", interval_min)
    return scheduler
