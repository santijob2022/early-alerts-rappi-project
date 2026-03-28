"""Settings loader using pydantic-settings.

Priority (highest → lowest):
  1. init kwargs
  2. environment variables (EARLY_ALERTS_*)
  3. .env file
  4. app/backend/data/config.yaml
  5. pydantic field defaults

This means docker-compose `environment:` values always override config.yaml,
which was NOT the case with the old `model_validate(yaml_dict)` approach that
incorrectly treated yaml values as init kwargs (priority 1).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Tuple, Type

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_DATA_DIR = Path(__file__).parent.parent / "data"
_CONFIG_YAML = _DATA_DIR / "config.yaml"


class ProviderSettings(BaseModel):
    name: str = "open_meteo"
    base_url: str = "https://api.open-meteo.com/v1/forecast"
    timeout_seconds: int = 30
    max_retries: int = 2


class PollingSettings(BaseModel):
    default_interval_minutes: int = 60
    elevated_interval_minutes: int = 15


class StorageSettings(BaseModel):
    sqlite_path: str = "data/alerts.db"
    duckdb_path: str = "data/forecast_warehouse.duckdb"


class Module3Settings(BaseModel):
    outbox_enabled: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EARLY_ALERTS_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    version: int = 1
    city: str = "monterrey"
    timezone: str = "America/Monterrey"
    provider: ProviderSettings = ProviderSettings()
    polling: PollingSettings = PollingSettings()
    storage: StorageSettings = StorageSettings()
    rule_pack_file: str = "rule_pack_v1.yaml"
    zone_catalog_file: str = "monterrey_zones.yaml"
    module3: Module3Settings = Module3Settings()
    earnings_baseline_mxn: float = 55.6
    # Set to true only in the dedicated scheduler process/container.
    # Keeps API workers from spawning duplicate scheduler instances.
    enable_scheduler: bool = False

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        # env vars (priority 2) beat yaml (priority 4) — docker-compose overrides work correctly.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=str(_CONFIG_YAML)),
            file_secret_settings,
        )

    @property
    def rule_pack_path(self) -> Path:
        return _DATA_DIR / self.rule_pack_file

    @property
    def zone_catalog_path(self) -> Path:
        return _DATA_DIR / self.zone_catalog_file

    @property
    def baseline_ratios_path(self) -> Path:
        return _DATA_DIR / "baseline_ratios.yaml"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (YAML defaults + env overrides)."""
    return Settings()
