"""JSON data provider for isolation mode.

This allows the UI API to operate without importing the external quant
engine Python packages. Instead, the quant system (or a build step)
emits structured JSON files the API reads read-only.

Directory contract (defaults assume QUANT_CORE_ROOT=<root>):

  catalog_root (default: <root>/catalog)
    features.json      -> {"features": [{"name": str, "description": str, "group": str}, ...]}
    primitives.json    -> {"primitives": [{"name": str, "description": str, "arity": int, "category": str}, ...]}

  strategies_root (default: <root>/strategies_json)
    list.json          -> {"items": [ <StrategySummaryLike> ... ]}
    <expr_hash>.json   -> full detail with optional tags/notes and metrics

  curves_root (default: <root>/equity_curves)
    <expr_hash>.json   -> {"dates": [...], "equity": [...], "base_currency": "USD"}
    (Optional) returns/<expr_hash>.json -> {"dates": [...], "returns": [...]} if precomputed

Strategy JSON shape examples:

Strategy summary/detail object:
{
  "expr_hash": "abc123",
  "expr": "zscore(feat('close')) > 0",
  "metrics": {"ann_return": 0.12, "ann_vol": 0.10, "ann_sharpe": 1.2, "max_dd": -0.08},
  "complexity_score": 14.2,
  "created_at": "2025-09-16T10:11:00Z",
  "tags": ["momentum"],
  "notes": "Optional free text"
}

All numeric metrics are floats; created_at is ISO8601 string.

If nested "metrics" absent you may provide top-level ann_return / ann_vol / ann_sharpe / max_dd.

Environment overrides:
  QUANT_DISABLE_ADAPTER=true    -> forces JSON mode even if quant_core modules import
  QUANT_CATALOG_ROOT            -> overrides catalog_root
  QUANT_STRATEGIES_ROOT         -> overrides strategies_root
  QUANT_CURVES_ROOT             -> overrides curves_root

Error handling: Missing files return None so callers can fall back to in-memory samples.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import json

from app.core.config import get_settings
from app.api.v1.schemas import (
    FeatureCatalogResponse,
    FeatureDefinition,
    PrimitiveCatalogResponse,
    PrimitiveDefinition,
    StrategyListResponse,
    StrategySummary,
    StrategyDetail,
    StrategyMetrics,
    EquityCurve,
    DailyReturns,
)


def _read_json(path: Path) -> Any | None:
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # pragma: no cover simple defensive
        return None


def load_feature_catalog() -> FeatureCatalogResponse | None:
    settings = get_settings()
    root = Path(settings.catalog_root or "catalog")
    data = _read_json(root / "features.json")
    if not data:
        return None
    feats: list[FeatureDefinition] = []
    for f in data.get("features", []):
        feats.append(
            FeatureDefinition(
                name=f.get("name"),
                description=f.get("description", ""),
                group=f.get("group", "other"),
            )
        )
    return FeatureCatalogResponse(features=feats)


def load_primitive_catalog() -> PrimitiveCatalogResponse | None:
    settings = get_settings()
    root = Path(settings.catalog_root or "catalog")
    data = _read_json(root / "primitives.json")
    if not data:
        return None
    prims: list[PrimitiveDefinition] = []
    for p in data.get("primitives", []):
        prims.append(
            PrimitiveDefinition(
                name=p.get("name"),
                description=p.get("description", ""),
                arity=p.get("arity", 0),
                category=p.get("category", "misc"),
            )
        )
    return PrimitiveCatalogResponse(primitives=prims)


def load_strategies(limit: int, offset: int) -> StrategyListResponse | None:
    settings = get_settings()
    root = Path(settings.strategies_root or "strategies_json")
    data = _read_json(root / "list.json")
    if not data:
        return None
    raw_items = data.get("items", [])
    items: list[StrategySummary] = []
    for r in raw_items[offset : offset + limit]:
        metrics_obj = r.get("metrics", r)
        metrics = StrategyMetrics(
            ann_return=metrics_obj.get("ann_return", 0.0),
            ann_vol=metrics_obj.get("ann_vol", 0.0),
            ann_sharpe=metrics_obj.get("ann_sharpe", 0.0),
            max_dd=metrics_obj.get("max_dd", 0.0),
        )
        items.append(
            StrategySummary(
                expr_hash=r.get("expr_hash"),
                expr=r.get("expr"),
                metrics=metrics,
                complexity_score=r.get("complexity_score", 0.0),
                created_at=r.get("created_at"),
            )
        )
    return StrategyListResponse(
        items=items, total=len(raw_items), limit=limit, offset=offset
    )


def load_strategy_detail(expr_hash: str) -> StrategyDetail | None:
    settings = get_settings()
    root = Path(settings.strategies_root or "strategies_json")
    data = _read_json(root / f"{expr_hash}.json")
    if not data:
        return None
    metrics_obj = data.get("metrics", data)
    metrics = StrategyMetrics(
        ann_return=metrics_obj.get("ann_return", 0.0),
        ann_vol=metrics_obj.get("ann_vol", 0.0),
        ann_sharpe=metrics_obj.get("ann_sharpe", 0.0),
        max_dd=metrics_obj.get("max_dd", 0.0),
    )
    return StrategyDetail(
        expr_hash=data.get("expr_hash"),
        expr=data.get("expr"),
        metrics=metrics,
        complexity_score=data.get("complexity_score", 0.0),
        created_at=data.get("created_at"),
        tags=data.get("tags", []),
        notes=data.get("notes"),
    )


def load_equity_curve(expr_hash: str) -> EquityCurve | None:
    settings = get_settings()
    root = Path(settings.curves_root or "equity_curves")
    data = _read_json(root / f"{expr_hash}.json")
    if not data:
        return None
    return EquityCurve(
        expr_hash=expr_hash,
        base_currency=data.get("base_currency", "USD"),
        dates=data.get("dates", []),
        equity=data.get("equity", []),
    )


def load_daily_returns(expr_hash: str) -> DailyReturns | None:
    settings = get_settings()
    root = Path(settings.curves_root or "equity_curves")
    # Try explicit returns file first
    ret_data = _read_json(root / "returns" / f"{expr_hash}.json")
    if ret_data and ret_data.get("returns"):
        return DailyReturns(
            expr_hash=expr_hash,
            dates=ret_data.get("dates", []),
            returns=ret_data.get("returns", []),
        )
    # Derive from equity if possible
    curve = load_equity_curve(expr_hash)
    if not curve or len(curve.equity) < 2:
        return None
    eq = curve.equity
    returns = []
    dates = curve.dates[1:]
    for i in range(1, len(eq)):
        try:
            returns.append(round(eq[i] / eq[i - 1] - 1, 6))
        except Exception:
            returns.append(0.0)
    return DailyReturns(expr_hash=expr_hash, dates=dates, returns=returns)


__all__ = [
    "load_feature_catalog",
    "load_primitive_catalog",
    "load_strategies",
    "load_strategy_detail",
    "load_equity_curve",
    "load_daily_returns",
]
