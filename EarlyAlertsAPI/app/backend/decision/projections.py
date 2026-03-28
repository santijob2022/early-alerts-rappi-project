"""Baseline ratio lookup + rain bucket + projected ratio calculation.

Pure functions – no I/O.
"""
from __future__ import annotations

import unicodedata

from app.backend.core.constants import RainBucket
from app.backend.core.rule_pack import RulePack


def _normalize_zone(zone: str) -> str:
    """Strip diacritics so parquet-derived keys match catalog names."""
    nfd = unicodedata.normalize("NFD", zone)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def bucketize_rain(mm: float, rule_pack: RulePack) -> RainBucket:
    """Map precipitation mm to a RainBucket per rule pack thresholds."""
    if mm < rule_pack.rain_buckets.dry_threshold:
        return RainBucket.DRY
    if mm < rule_pack.rain_buckets.moderate_threshold:
        return RainBucket.LIGHT
    if mm < rule_pack.rain_buckets.heavy_threshold:
        return RainBucket.MODERATE
    return RainBucket.HEAVY


def project_ratio(
    zone: str,
    forecast_hour: int,
    precip_mm: float,
    rule_pack: RulePack,
    baseline_table: dict,
) -> float:
    """Apply rain lift to dry baseline ratio for this zone×hour.

    Fallback chain:
      1. by_zone_hour[zone][hour]
      2. by_zone_period[zone][peak|offpeak]
      3. by_zone[zone]
      4. city-wide average (mean of by_zone)
    """
    zone_key = _normalize_zone(zone)
    is_peak = forecast_hour in rule_pack.peak_hours

    # --- baseline lookup -------------------------------------------------
    baseline = (
        baseline_table.get("by_zone_hour", {}).get(zone_key, {}).get(forecast_hour)
        or baseline_table.get("by_zone_period", {})
        .get(zone_key, {})
        .get("peak" if is_peak else "offpeak")
        or baseline_table.get("by_zone", {}).get(zone_key)
    )
    if baseline is None:
        all_zone_ratios = list(baseline_table.get("by_zone", {}).values())
        baseline = sum(all_zone_ratios) / len(all_zone_ratios) if all_zone_ratios else 1.0

    # --- lift selection --------------------------------------------------
    bucket = bucketize_rain(precip_mm, rule_pack)
    if bucket == RainBucket.DRY:
        lift = 0.0
    else:
        period_lifts = rule_pack.rain_lifts.peak if is_peak else rule_pack.rain_lifts.offpeak
        lift = {
            RainBucket.LIGHT: period_lifts.light,
            RainBucket.MODERATE: period_lifts.moderate,
            RainBucket.HEAVY: period_lifts.heavy,
        }[bucket]

    projected = baseline + lift

    # --- sensitive-peak floor override -----------------------------------
    if (
        is_peak
        and zone in rule_pack.sensitive_zones
        and rule_pack.triggers.sensitive_peak_mm
        <= precip_mm
        < rule_pack.triggers.base_mm
    ):
        floor = rule_pack.sensitive_peak_floors.get(zone)
        if floor is not None:
            projected = max(projected, floor)

    return round(projected, 4)
