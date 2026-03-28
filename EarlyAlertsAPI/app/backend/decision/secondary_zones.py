"""Secondary-zone ranking algorithm.

Pure function – no I/O.
"""
from __future__ import annotations

import math

from app.backend.core.rule_pack import RulePack
from app.backend.core.zone_catalog import ZoneCatalog


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (Haversine formula)."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _tier(zone: str, rule_pack: RulePack) -> int:
    """Return sort priority: 0=sensitive, 1=volume, 2=other."""
    if zone in rule_pack.sensitive_zones:
        return 0
    if zone in rule_pack.volume_monitors:
        return 1
    return 2


def rank_secondary_zones(
    primary_zone: str,
    zone_forecasts: dict[str, float],  # zone → precip_mm at t+1
    rule_pack: RulePack,
    zone_catalog: ZoneCatalog,
) -> list[str]:
    """Return up to 2 secondary zones ordered by sensitivity tier, then
    precip descending, then proximity ascending.
    """
    wet_threshold = 1.0
    candidates = [
        z
        for z, mm in zone_forecasts.items()
        if z != primary_zone and mm >= wet_threshold
    ]

    if not candidates:
        return list(rule_pack.secondary_zones.fallback_neighbors.get(primary_zone, []))[
            :rule_pack.secondary_zones.max_count
        ]

    try:
        p_lat, p_lon = zone_catalog.get_centroid(primary_zone)
    except KeyError:
        p_lat, p_lon = 0.0, 0.0

    def sort_key(zone: str) -> tuple:
        mm = zone_forecasts.get(zone, 0.0)
        try:
            z_lat, z_lon = zone_catalog.get_centroid(zone)
            dist = _haversine_km(p_lat, p_lon, z_lat, z_lon)
        except KeyError:
            dist = 9999.0
        return (_tier(zone, rule_pack), -mm, dist)

    candidates.sort(key=sort_key)
    return candidates[: rule_pack.secondary_zones.max_count]
