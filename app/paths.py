from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Optional, Union

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "paths.yaml"
ENV_DATA_ROOT = "DATA_ROOT"


@dataclass(frozen=True)
class DataPaths:
    data_root: Path
    calendar: Path
    instruments_all: Path
    instruments_indexes: Path
    market_neutral_alpha360: Path
    features_vol: Path
    features_liquidity: Path
    features_sector: Path
    sector_map: Path
    instrument_blackouts: Path
    exogenous_fx: Path
    exogenous_daily: Path

    @property
    def qlib_provider_uri(self) -> str:
        return str(self.data_root)


def _read_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _resolve_data_root(config: dict) -> Path:
    data_root_value = os.environ.get(ENV_DATA_ROOT) or config.get("data_root")
    if not data_root_value:
        raise ValueError("data_root is required in configs/paths.yaml or DATA_ROOT")

    data_root_str = str(data_root_value)
    windows_abs = PureWindowsPath(data_root_str).is_absolute()

    if os.name != "nt" and windows_abs:
        if len(data_root_str) >= 2 and data_root_str[1] == ":":
            drive = data_root_str[0].lower()
            tail = data_root_str[2:].lstrip("\\/").replace("\\", "/")
            data_root_str = f"/mnt/{drive}/{tail}"
        else:
            raise ValueError("Windows UNC paths are not supported on non-Windows hosts")

    data_root = Path(data_root_str).expanduser()
    if not data_root.is_absolute() and not windows_abs:
        raise ValueError("data_root must be an absolute path (e.g., C:/data/xsto)")

    return data_root.resolve()


def load_paths(config_path: Optional[Union[Path, str]] = None) -> DataPaths:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    config = _read_config(path)
    data_root = _resolve_data_root(config)

    return DataPaths(
        data_root=data_root,
        calendar=data_root / "calendars" / "day.txt",
        instruments_all=data_root / "instruments" / "all.txt",
        instruments_indexes=data_root / "instruments" / "indexes.txt",
        market_neutral_alpha360=data_root
        / "market_neutral_features"
        / "market_neutral_alpha360.parquet",
        features_vol=data_root / "features_vol.parquet",
        features_liquidity=data_root / "features_liquidity.parquet",
        features_sector=data_root / "features_sector.parquet",
        sector_map=data_root / "meta" / "sector_map.parquet",
        instrument_blackouts=data_root / "meta" / "instrument_blackouts.parquet",
        exogenous_fx=data_root / "exogenous" / "fx.parquet",
        exogenous_daily=data_root / "exogenous" / "exog_daily.parquet",
    )


def validate_paths(paths: DataPaths) -> tuple[list[str], list[str]]:
    required = {
        "data_root": paths.data_root,
        "calendar": paths.calendar,
        "instruments_all": paths.instruments_all,
        "instruments_indexes": paths.instruments_indexes,
    }
    optional = {
        "market_neutral_alpha360": paths.market_neutral_alpha360,
        "features_vol": paths.features_vol,
        "features_liquidity": paths.features_liquidity,
        "features_sector": paths.features_sector,
        "sector_map": paths.sector_map,
        "instrument_blackouts": paths.instrument_blackouts,
        "exogenous_fx": paths.exogenous_fx,
        "exogenous_daily": paths.exogenous_daily,
    }

    missing_required = [name for name, path in required.items() if not path.exists()]
    missing_optional = [name for name, path in optional.items() if not path.exists()]
    return missing_required, missing_optional
