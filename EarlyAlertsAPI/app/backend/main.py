"""FastAPI application factory + lifespan."""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path

import yaml
from fastapi import FastAPI

from app.backend.api.router import api_router
from app.backend.core.config import get_settings
from app.backend.core.rule_pack import load_rule_pack
from app.backend.core.zone_catalog import load_zone_catalog
from app.backend.state.database import init_db

# Ensure all app.* loggers are visible in container stdout alongside uvicorn logs.
# Uvicorn configures its own handlers but leaves the root logger untouched, so
# without this, any logger outside the uvicorn.* hierarchy is silently dropped.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    init_db(settings.storage.sqlite_path)
    rule_pack = load_rule_pack(str(settings.rule_pack_path))
    zone_catalog = load_zone_catalog(str(settings.zone_catalog_path))
    with open(settings.baseline_ratios_path, encoding="utf-8") as fh:
        baseline_table = yaml.safe_load(fh)

    application.state.settings = settings
    application.state.rule_pack = rule_pack
    application.state.zone_catalog = zone_catalog
    application.state.baseline_table = baseline_table

    # Startup debug log: shows resolved settings for visibility in container logs.
    # TODO: remove this log in production deployments once configuration is validated.
    logger = logging.getLogger("app.backend.main")
    logger.info(
        "startup: enable_scheduler=%s sqlite=%s duckdb=%s provider=%s",
        settings.enable_scheduler,
        settings.storage.sqlite_path,
        settings.storage.duckdb_path,
        settings.provider.base_url,
    )

    # Start scheduler only when explicitly enabled.
    # In multi-worker deployments set EARLY_ALERTS_ENABLE_SCHEDULER=true
    # on exactly one process (the dedicated scheduler container).
    if settings.enable_scheduler:
        try:
            from app.backend.services.scheduler import start_scheduler
            scheduler = start_scheduler(application)
            application.state.scheduler = scheduler
        except Exception:
            logging.getLogger("app.backend.main").exception(
                "Scheduler failed to start — API will continue without it"
            )

    yield

    # Shutdown scheduler if running
    scheduler_instance = getattr(application.state, "scheduler", None)
    if scheduler_instance and scheduler_instance.running:
        scheduler_instance.shutdown(wait=False)


def create_app() -> FastAPI:
    application = FastAPI(
        title="Early Alerts API",
        version="0.1.0",
        description="Weather-driven alert outbox for dynamic pricing – Module 2c",
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix="/api/v1")
    return application


# Allow `uvicorn app.backend.main:app` direct usage
app = create_app()
