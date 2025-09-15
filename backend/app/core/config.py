"""Configuration helpers for the FastAPI service."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the environment."""

    app_name: str = "Quant UI API"
    version: str = "0.1.0"
    git_commit: str | None = None

    db_path: str = Field(default="./runs.sqlite", alias="DB_PATH")
    data_root: str = Field(default="./data_curated", alias="DATA_ROOT")
    raw_root: str = Field(default="./data_raw", alias="RAW_ROOT")
    api_key: str | None = Field(default=None, alias="API_KEY")
    broker_mode: str = "dummy"

    model_config = SettingsConfigDict(env_prefix="QUANT_", env_file=".env", extra="ignore")

    def model_post_init(self, __context: Any) -> None:
        """Apply environment overrides that do not share the QUANT_ prefix."""

        broker_override = os.getenv("BROKER_MODE")
        if broker_override:
            object.__setattr__(self, "broker_mode", broker_override)


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of :class:`Settings`."""

    return Settings()


__all__ = ["Settings", "get_settings"]
