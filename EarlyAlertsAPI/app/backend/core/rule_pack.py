"""Typed rule-pack loader.

All calibrated constants live exclusively in rule_pack_v1.yaml.
This module loads and validates that file into a RulePack model.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class TriggerConfig(BaseModel, frozen=True):
    base_mm: float
    sensitive_peak_mm: float
    critical_escalation_mm: float


class RainBucketConfig(BaseModel, frozen=True):
    dry_threshold: float
    moderate_threshold: float
    heavy_threshold: float


class PeakOffpeakLifts(BaseModel, frozen=True):
    light: float
    moderate: float
    heavy: float


class RainLifts(BaseModel, frozen=True):
    peak: PeakOffpeakLifts
    offpeak: PeakOffpeakLifts


class SeverityThresholds(BaseModel, frozen=True):
    medio_min: float
    alto_min: float
    critico_min: float


class EarningsConfig(BaseModel, frozen=True):
    target_mxn: float
    baseline_city_mxn: float
    rainy_peak_median_mxn: float


class MemoryConfig(BaseModel, frozen=True):
    cooldown_hours: int
    dry_close_streak_hours: int
    dry_threshold_mm: float
    resend_precip_delta_mm: float
    resend_earnings_delta_mxn: float


class SecondaryZonesConfig(BaseModel, frozen=True):
    max_count: int
    fallback_neighbors: dict[str, list[str]]


class HorizonConfig(BaseModel, frozen=True):
    primary_minutes: int
    watchlist_max_minutes: int


class RulePack(BaseModel, frozen=True):
    version: str
    source: str
    triggers: TriggerConfig
    peak_hours: list[int]
    sensitive_zones: list[str]
    volume_monitors: list[str]
    rain_buckets: RainBucketConfig
    rain_lifts: RainLifts
    sensitive_peak_floors: dict[str, float]
    severity_thresholds: SeverityThresholds
    earnings: EarningsConfig
    memory: MemoryConfig
    secondary_zones: SecondaryZonesConfig
    horizons: HorizonConfig


def load_rule_pack(path: Path | str) -> RulePack:
    """Parse a rule-pack YAML file into a validated RulePack."""
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return RulePack.model_validate(raw)
