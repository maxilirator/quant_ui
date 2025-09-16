"""Load strategies from quant core config JSON files (strategies_default / sweep).

This sits between the dynamic adapter import path and the JSON provider. It
parses `configs/strategies_default.json` and `configs/strategies_sweep.json` in
the external quant root (QUANT_CORE_ROOT) and synthesises StrategySummary /
StrategyDetail objects so the UI can display *real* configured strategies even
before training artifacts / manifests exist.

Assumptions
-----------
* Each file has shape: {"strategies": [ {"name": str, "params": {...}, "tags": [...],
  "metadata": {"description": str, ...}, "enabled": bool, ... }, ... ] }
* No explicit expression DSL is present; we derive a pseudo expr from name.
* Metrics are not stored; we create deterministic placeholder metrics so that
  UI charts/layout are populated while awaiting true performance data.

Deterministic Metrics
---------------------
We hash the strategy name and map to plausible ranges:
  ann_return: 5% ± 3%
  ann_vol:    10% ± 2%
  ann_sharpe: 0.6  ± 0.8 (clamped >= -0.2)
  max_dd:    -(5% to 20%)

These are purely cosmetic and MUST NOT be interpreted as real backtest output.
"""

from __future__ import annotations

from pathlib import Path
import json
import hashlib
from datetime import datetime, timezone
from typing import Iterable

from app.core.config import get_settings
from app.api.v1.schemas import (
    StrategyListResponse,
    StrategySummary,
    StrategyDetail,
    StrategyMetrics,
)

UTC = timezone.utc


def _read(path: Path):  # defensive JSON reader
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # pragma: no cover
        return None


def _det_metrics(name: str) -> StrategyMetrics:
    h = hashlib.sha256(name.encode()).hexdigest()
    bucket = int(h[:8], 16)

    def _rng(span: float, base: float, shift_bits: int) -> float:
        return base + ((bucket >> shift_bits) & 0xFFFF) / 0xFFFF * span - span / 2

    ann_return = 0.05 + _rng(0.06, 0, 0)  # 5% +/-3%
    ann_vol = 0.10 + _rng(0.04, 0, 4)  # 10% +/-2%
    ann_sharpe = 0.6 + _rng(0.8, 0, 8)  # 0.6 +/-0.4 approx
    max_dd = -0.05 - abs(_rng(0.15, 0, 12))  # -5% to about -20%
    return StrategyMetrics(
        ann_return=round(ann_return, 4),
        ann_vol=round(abs(ann_vol), 4),
        ann_sharpe=round(ann_sharpe, 2),
        max_dd=round(max_dd, 4),
    )


def _strategy_iter() -> Iterable[StrategyDetail]:
    settings = get_settings()
    root = settings.quant_core_root
    if not root:
        return []
    cfg_dir = Path(root) / "configs"
    default_path = cfg_dir / "strategies_default.json"
    sweep_path = cfg_dir / "strategies_sweep.json"
    seen: set[str] = set()
    for path in (default_path, sweep_path):
        data = _read(path)
        if not data:
            continue
        strategies = data.get("strategies", [])
        for s in strategies:
            name = s.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            tags = s.get("tags", []) or []
            meta = s.get("metadata", {}) or {}
            desc = meta.get("description")
            created_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            metrics = _det_metrics(name)
            detail = StrategyDetail(
                expr_hash=name,  # using name as stable hash surrogate
                expr=f"strategy_config('{name}')",  # synthetic expression marker
                metrics=metrics,
                complexity_score=len(name) * 1.0,
                created_at=created_at,
                tags=tags,
                notes=desc,
            )
            yield detail


def _apply_order(
    items: list[StrategyDetail], order: str | None
) -> list[StrategyDetail]:
    if not order:
        return items
    # Support comma separated multi-key order e.g. "ann_return_desc,ann_sharpe_desc,max_dd_asc"
    keys = [k.strip() for k in order.split(",") if k.strip()]
    # We apply in reverse so the first key has highest precedence (stable sort property)
    for key in reversed(keys):
        parts = key.split("_")
        if len(parts) < 2:
            field = key
            direction = "asc"
        else:
            field = "_".join(parts[:-1])
            direction = parts[-1]
        reverse = direction.lower() == "desc"
        if field in {"ann_return", "ann_vol", "ann_sharpe", "max_dd"}:
            items.sort(key=lambda s: getattr(s.metrics, field), reverse=reverse)
        elif field == "created_at":
            items.sort(key=lambda s: s.created_at, reverse=reverse)
        elif field in {"name", "expr_hash"}:
            items.sort(key=lambda s: s.expr_hash.lower(), reverse=reverse)
        elif field == "complexity_score":
            items.sort(key=lambda s: s.complexity_score, reverse=reverse)
        # Ignore unknown fields silently
    return items


def load_config_strategies(
    limit: int, offset: int, order: str | None = None
) -> StrategyListResponse | None:
    items = list(_strategy_iter())
    if not items:
        return None
    items = _apply_order(items, order)
    total = len(items)
    sliced = items[offset : offset + limit]
    return StrategyListResponse(
        items=sliced, total=total, limit=limit, offset=offset, order=order
    )


def load_config_strategy_detail(expr_hash: str) -> StrategyDetail | None:
    for s in _strategy_iter():
        if s.expr_hash == expr_hash:
            return s
    return None


__all__ = ["load_config_strategies", "load_config_strategy_detail"]
