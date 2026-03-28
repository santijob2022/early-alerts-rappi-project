"""Pydantic domain models used across the backend.

All models are frozen (immutable) to guarantee thread-safety and
predictable behaviour inside the decision engine.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.backend.core.constants import (
    DecisionType,
    EventStatus,
    OutboxStatus,
    RiskLevel,
)


class ZoneInfo(BaseModel, frozen=True):
    name: str
    latitude: float
    longitude: float
    description: str


class ZoneForecastRow(BaseModel, frozen=True):
    zone: str
    forecast_hour: int = Field(ge=0, le=23)
    forecast_time: datetime
    precip_mm: float = Field(ge=0.0)
    fetched_at: datetime
    run_id: str


class DecisionInput(BaseModel, frozen=True):
    zone: str
    forecast_hour: int = Field(ge=0, le=23)
    forecast_precip_mm: float = Field(ge=0.0)
    current_hour: int = Field(ge=0, le=23)
    current_earnings_mxn: float = Field(default=55.6)


class DecisionOutput(BaseModel, frozen=True):
    decision_type: DecisionType
    risk_level: RiskLevel | None = None
    projected_ratio: float | None = None
    recommended_earnings_mxn: float = 55.6
    uplift_mxn: float = 0.0
    lead_time_min: int = 60
    secondary_zones: list[str] = Field(default_factory=list)
    reason: str = ""


class OutboxRecord(BaseModel):
    id: str
    event_id: str
    city: str
    zone: str
    forecast_time: datetime
    precip_mm: float
    risk_level: RiskLevel
    projected_ratio: float
    recommended_earnings_mxn: float
    uplift_mxn: float
    lead_time_min: int
    secondary_zones: list[str]
    reason: str
    decision_type: DecisionType
    status: OutboxStatus
    run_id: str
    source_snapshot_id: str
    rule_pack_version: str
    created_at: datetime
    consumed_at: datetime | None = None


class AlertEvent(BaseModel):
    id: str
    city: str
    zone: str
    opened_at: str
    closed_at: str | None = None
    last_sent_at: str | None = None
    max_risk: str | None = None
    max_precip_mm: float | None = None
    status: EventStatus
    dry_streak: int = 0


class RunSummary(BaseModel):
    run_id: str
    status: str
    zones_evaluated: int
    alerts_emitted: int
    snapshot_id: str | None = None
    error: str | None = None
