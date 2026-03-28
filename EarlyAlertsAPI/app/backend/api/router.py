"""Central APIRouter aggregator."""
from __future__ import annotations

from fastapi import APIRouter

from app.backend.api.alerts import router as alerts_router
from app.backend.api.config_routes import router as config_router
from app.backend.api.events import router as events_router
from app.backend.api.health import router as health_router
from app.backend.api.jobs import router as jobs_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(config_router)
api_router.include_router(alerts_router)
api_router.include_router(events_router)
api_router.include_router(jobs_router)
