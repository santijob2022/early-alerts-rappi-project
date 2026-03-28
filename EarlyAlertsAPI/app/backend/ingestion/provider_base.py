"""Abstract base class for weather forecast providers."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ForecastProvider(ABC):
    """Common interface for weather data sources.

    Swapping to WeatherAPI, OpenWeatherMap, etc. must not touch decision code –
    only a new concrete subclass is needed.
    """

    @abstractmethod
    async def fetch_hourly_forecast(
        self,
        coordinates: list[tuple[float, float]],
        hours_ahead: int = 6,
    ) -> list[dict]:
        """Fetch hourly forecast for a batch of (lat, lon) pairs.

        Args:
            coordinates: List of (latitude, longitude) tuples.
            hours_ahead: How many future hours to retrieve.

        Returns:
            Raw forecast dicts – one per coordinate, in the same order.
        """
        ...
