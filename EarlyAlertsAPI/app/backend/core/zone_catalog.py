"""Zone catalog loader and centroid helpers."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.backend.core.models import ZoneInfo


class ZoneCatalog(BaseModel, frozen=True):
    city: str
    timezone: str
    zones: list[ZoneInfo]

    def get_centroid(self, zone_name: str) -> tuple[float, float]:
        """Return (latitude, longitude) for the named zone."""
        for z in self.zones:
            if z.name == zone_name:
                return (z.latitude, z.longitude)
        raise KeyError(f"Zone '{zone_name}' not found in catalog")

    def zone_names(self) -> list[str]:
        return [z.name for z in self.zones]

    def all_centroids(self) -> list[tuple[float, float]]:
        """Return centroids in zone-catalog order (lat, lon)."""
        return [(z.latitude, z.longitude) for z in self.zones]

    def distance_km(self, zone_a: str, zone_b: str) -> float:
        """Haversine distance in km between two zone centroids."""
        lat1, lon1 = self.get_centroid(zone_a)
        lat2, lon2 = self.get_centroid(zone_b)
        return _haversine(lat1, lon1, lat2, lon2)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_zone_catalog(path: Path | str) -> ZoneCatalog:
    """Parse a zone-catalog YAML file into a validated ZoneCatalog."""
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ZoneCatalog.model_validate(raw)
