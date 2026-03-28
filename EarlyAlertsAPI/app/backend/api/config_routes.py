"""GET /api/v1/config"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/config")
async def get_config(request: Request) -> dict:
    """Return the resolved runtime settings as a JSON-serializable dict.

    Returns the application's effective configuration (the `Settings` model
    after environment overrides and defaults are applied). This is useful for
    debugging, validating environment variable overrides, or displaying the
    current configuration in an admin UI.

    Note: the implementation currently assumes there are no secrets to redact
    in v1. Treat this endpoint as sensitive — restrict access in
    non-development environments.
    """
    return request.app.state.settings.model_dump()
