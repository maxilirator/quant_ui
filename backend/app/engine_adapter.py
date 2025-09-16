"""Engine adapter: bridges this UI FastAPI service to an external quant engine.

The external engine root is supplied via QUANT_CORE_ROOT / CORE_ROOT environment
variables (already handled by settings & sys.path injection in main.py).

This adapter performs *best-effort* imports. If unavailable, endpoints fall back
on static sample data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import asyncio

from app.api.v1.schemas import (
    StrategyListResponse,
    StrategySummary,
    StrategyDetail,
    StrategyMetrics,
    EquityCurve,
    FeatureCatalogResponse,
    FeatureDefinition,
    PrimitiveCatalogResponse,
    PrimitiveDefinition,
)

# Detection flags
_TRIED_IMPORT = False
_AVAILABLE = False

# Cached callables (if discovered)
_list_strategies_fn = None
_get_strategy_fn = None
_get_equity_fn = None
_get_feature_catalog_fn = None
_get_primitive_catalog_fn = None


def _attempt_import() -> None:
    global _TRIED_IMPORT, _AVAILABLE
    if _TRIED_IMPORT:
        return
    _TRIED_IMPORT = True
    # Probing common module names; adjust if external API differs
    candidates = [
        ("quant_core.api", ["list_strategies", "get_strategy_detail"]),
        ("quant_core.results", ["equity_curve"]),
        ("quant_core.catalog", ["feature_catalog", "primitive_catalog"]),
    ]
    import importlib

    found_any = False
    for mod_name, symbols in candidates:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        found_any = True
        for sym in symbols:
            fn = getattr(mod, sym, None)
            if fn is None:
                continue
            if sym == "list_strategies":
                globals()["_list_strategies_fn"] = fn
            elif sym == "get_strategy_detail":
                globals()["_get_strategy_fn"] = fn
            elif sym == "equity_curve":
                globals()["_get_equity_fn"] = fn
            elif sym == "feature_catalog":
                globals()["_get_feature_catalog_fn"] = fn
            elif sym == "primitive_catalog":
                globals()["_get_primitive_catalog_fn"] = fn
    _AVAILABLE = found_any


def adapter_available() -> bool:
    _attempt_import()
    return _AVAILABLE


async def fetch_strategies(limit: int, offset: int) -> StrategyListResponse:
    _attempt_import()
    if not _list_strategies_fn:
        raise RuntimeError("External engine list_strategies not available")
    # Assume external returns list[dict] with keys aligning to our schema.
    rows = _list_strategies_fn(limit=limit, offset=offset)  # type: ignore
    items: list[StrategySummary] = []
    for r in rows:
        metrics = StrategyMetrics(
            ann_return=r.get("ann_return", r.get("metrics", {}).get("ann_return", 0.0)),
            ann_vol=r.get("ann_vol", r.get("metrics", {}).get("ann_vol", 0.0)),
            ann_sharpe=r.get("ann_sharpe", r.get("metrics", {}).get("ann_sharpe", 0.0)),
            max_dd=r.get("max_dd", r.get("metrics", {}).get("max_dd", 0.0)),
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
        items=items, total=len(items), limit=limit, offset=offset
    )


async def fetch_strategy_detail(expr_hash: str) -> Optional[StrategyDetail]:
    _attempt_import()
    if not _get_strategy_fn:
        return None
    r = _get_strategy_fn(expr_hash)  # type: ignore
    if not r:
        return None
    metrics = StrategyMetrics(
        ann_return=r.get("ann_return", r.get("metrics", {}).get("ann_return", 0.0)),
        ann_vol=r.get("ann_vol", r.get("metrics", {}).get("ann_vol", 0.0)),
        ann_sharpe=r.get("ann_sharpe", r.get("metrics", {}).get("ann_sharpe", 0.0)),
        max_dd=r.get("max_dd", r.get("metrics", {}).get("max_dd", 0.0)),
    )
    return StrategyDetail(
        expr_hash=r.get("expr_hash"),
        expr=r.get("expr"),
        metrics=metrics,
        complexity_score=r.get("complexity_score", 0.0),
        created_at=r.get("created_at"),
        tags=r.get("tags", []),
        notes=r.get("notes"),
    )


async def fetch_equity_curve(expr_hash: str) -> Optional[EquityCurve]:
    _attempt_import()
    if not _get_equity_fn:
        return None
    eq = _get_equity_fn(expr_hash)  # type: ignore
    if not eq:
        return None
    # Expect eq to be a dict {dates: [...], equity: [...], base_currency: 'SEK'} or similar
    dates = eq.get("dates") or eq.get("date") or []
    equity = eq.get("equity") or eq.get("values") or []
    base_ccy = eq.get("base_currency", "SEK")
    return EquityCurve(
        expr_hash=expr_hash, base_currency=base_ccy, dates=dates, equity=equity
    )


async def fetch_feature_catalog() -> Optional[FeatureCatalogResponse]:
    _attempt_import()
    if not _get_feature_catalog_fn:
        return None
    catalog = _get_feature_catalog_fn()  # type: ignore
    features: list[FeatureDefinition] = []
    for f in catalog:
        # Accept either dict or object with attributes
        name = getattr(f, "name", None) or f.get("name")
        desc = getattr(f, "description", None) or f.get("description", "")
        group = getattr(f, "group", None) or f.get("group", "other")
        features.append(FeatureDefinition(name=name, description=desc, group=group))
    return FeatureCatalogResponse(features=features)


async def fetch_primitive_catalog() -> Optional[PrimitiveCatalogResponse]:
    _attempt_import()
    if not _get_primitive_catalog_fn:
        return None
    primitives_raw = _get_primitive_catalog_fn()  # type: ignore
    prims: list[PrimitiveDefinition] = []
    for p in primitives_raw:
        name = getattr(p, "name", None) or p.get("name")
        desc = getattr(p, "description", None) or p.get("description", "")
        arity = getattr(p, "arity", None) or p.get("arity", 0)
        cat = getattr(p, "category", None) or p.get("category", "misc")
        prims.append(
            PrimitiveDefinition(name=name, description=desc, arity=arity, category=cat)
        )
    return PrimitiveCatalogResponse(primitives=prims)


__all__ = [
    "adapter_available",
    "fetch_strategies",
    "fetch_strategy_detail",
    "fetch_equity_curve",
    "fetch_feature_catalog",
    "fetch_primitive_catalog",
]
