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
    data_version: str | None = Field(default=None, alias="DATA_VERSION")

    db_path: str = Field(default="./runs.sqlite", alias="DB_PATH")
    data_root: str = Field(default="./data_curated", alias="DATA_ROOT")
    raw_root: str = Field(default="./data_raw", alias="RAW_ROOT")
    api_key: str | None = Field(default=None, alias="API_KEY")
    broker_mode: str = "dummy"
    # Optional path to external quant core / research engine root (e.g. /dev/quant)
    quant_core_root: str | None = Field(default=None, alias="CORE_ROOT")
    # Backwards/explicit env alias with prefix (QUANT_CORE_ROOT) also supported automatically by pydantic via env_prefix
    core_root: str | None = Field(default=None, alias="QUANT_CORE_ROOT")
    # Optional explicit artifacts root (defaults to ./artifacts or <quant_core_root>/artifacts)
    artifacts_root: str | None = Field(default=None, alias="ARTIFACTS_ROOT")
    # Isolation mode: disable dynamic adapter imports and use JSON files
    disable_adapter: bool = Field(default=False, alias="DISABLE_ADAPTER")
    catalog_root: str | None = Field(
        default=None, alias="CATALOG_ROOT"
    )  # where features.json & primitives.json live
    strategies_root: str | None = Field(
        default=None, alias="STRATEGIES_ROOT"
    )  # strategies/*.json
    curves_root: str | None = Field(
        default=None, alias="CURVES_ROOT"
    )  # curves/*.json or equity/*.json
    dev_mode: bool = Field(default=False, alias="DEV_MODE")
    # Optional explicit Python interpreter for quant core tasks (overrides sys.executable for job subprocesses)
    core_python: str | None = Field(default=None, alias="CORE_PYTHON")

    model_config = SettingsConfigDict(
        env_prefix="QUANT_", env_file=".env", extra="ignore"
    )

    def model_post_init(self, __context: Any) -> None:
        """Apply environment overrides that do not share the QUANT_ prefix."""

        broker_override = os.getenv("BROKER_MODE")
        if broker_override:
            object.__setattr__(self, "broker_mode", broker_override)

        # Harmonise quant_core_root precedence: explicit QUANT_CORE_ROOT > CORE_ROOT > provided field
        # Accept both CORE_ROOT (no prefix) and QUANT_CORE_ROOT for flexibility.
        prefixed = os.getenv("QUANT_CORE_ROOT")
        unprefixed = os.getenv("CORE_ROOT")
        chosen = prefixed or unprefixed or self.quant_core_root or self.core_root
        if chosen:
            object.__setattr__(self, "quant_core_root", chosen)

        # Resolve artifacts root precedence: explicit QUANT_ARTIFACTS_ROOT / ARTIFACTS_ROOT > provided field > quant_core_root/artifacts > ./artifacts
        artifacts_prefixed = os.getenv("QUANT_ARTIFACTS_ROOT") or os.getenv(
            "ARTIFACTS_ROOT"
        )
        artifacts_chosen = (
            artifacts_prefixed
            or self.artifacts_root
            or (f"{chosen}/artifacts" if chosen else None)
            or "./artifacts"
        )
        object.__setattr__(self, "artifacts_root", artifacts_chosen)

        # Fill JSON provider defaults if not explicitly set
        qroot = chosen
        if not self.catalog_root and qroot:
            object.__setattr__(self, "catalog_root", f"{qroot}/catalog")
        if not self.strategies_root and qroot:
            object.__setattr__(self, "strategies_root", f"{qroot}/strategies_json")
        if not self.curves_root and qroot:
            object.__setattr__(self, "curves_root", f"{qroot}/equity_curves")

        # Dev mode precedence: QUANT_DEV_MODE or DEV_MODE env overrides
        dev_env = os.getenv("QUANT_DEV_MODE") or os.getenv("DEV_MODE")
        if dev_env is not None:
            val = dev_env.lower() in {"1", "true", "yes", "on"}
            object.__setattr__(self, "dev_mode", val)

        # Resolve core python interpreter precedence:
        # 1. QUANT_CORE_PYTHON
        # 2. CORE_PYTHON (no prefix)
        # 3. Provided field value
        # 4. Auto-detect inside quant_core_root (.venv or venv) if exists
        py_prefixed = os.getenv("QUANT_CORE_PYTHON") or os.getenv("CORE_PYTHON")
        chosen_py = py_prefixed or self.core_python
        if not chosen_py and getattr(self, "quant_core_root", None):
            root = getattr(self, "quant_core_root")
            # Windows & POSIX candidates
            candidates = [
                f"{root}/.venv/Scripts/python.exe",
                f"{root}/.venv/bin/python",
                f"{root}/venv/Scripts/python.exe",
                f"{root}/venv/bin/python",
            ]
            for c in candidates:
                if os.path.exists(c):
                    chosen_py = c
                    break
        if chosen_py:
            object.__setattr__(self, "core_python", chosen_py)


@lru_cache
def get_settings() -> Settings:
    """Return a cached instance of :class:`Settings`."""

    return Settings()


__all__ = ["Settings", "get_settings"]
