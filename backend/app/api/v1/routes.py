"""Version 1 API routes (UI adapter mode).

This service is a thin read-only facade over an external quant engine
mounted via QUANT_CORE_ROOT (see `engine_adapter`). Strategy & feature
data are sourced from external artifacts (manifest / runs DB) when
available; otherwise a small in-memory fallback sample is returned.

Mutation endpoints from the earlier prototype (training/backtest/jobs)
now return HTTP 501 to signal that they are intentionally disabled in
the UI-only deployment profile.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket

UTC = timezone.utc

from app.core.config import Settings, get_settings

from .schemas import (
    AggregateMetrics,
    DailyReturns,
    EquityCurve,
    FeatureCatalogResponse,
    FeatureDefinition,
    HealthResponse,
    PrimitiveCatalogResponse,
    PrimitiveDefinition,
    CatalogManifest,
    CatalogArtifactCounts,
    CatalogStrategyTagStat,
    CatalogDatasetEntry,
    StrategyDetail,
    StrategyListResponse,
    StrategyMetrics,
    StrategySummary,
    StrategyAnalysis,
    StrategyAnalytics,
    DrawdownEvent,
)

from app.engine_adapter import (
    adapter_available,
    fetch_equity_curve,
    fetch_feature_catalog,
    fetch_primitive_catalog,
    fetch_strategy_detail,
    fetch_strategies,
)
from app.providers.json_provider import (
    load_feature_catalog as json_feature_catalog,
    load_primitive_catalog as json_primitive_catalog,
    load_strategies as json_list_strategies,
    load_strategy_detail as json_strategy_detail,
    load_equity_curve as json_equity_curve,
    load_daily_returns as json_daily_returns,
)
from app.providers.config_strategy_provider import (
    load_config_strategies,
    load_config_strategy_detail,
)
from .panel import load_panel_slice
from app.artifacts.manifest import load_manifest
from pathlib import Path
from collections import Counter
import math
import hashlib

router = APIRouter()


SettingsDep = Annotated[Settings, Depends(get_settings)]


NOW = datetime.now(UTC)

SAMPLE_STRATEGIES: dict[str, StrategyDetail] = {
    "abc123": StrategyDetail(
        expr_hash="abc123",
        expr='clip(feat("c_sek")/lag(feat("c_sek"),1)-1)',
        metrics=StrategyMetrics(
            ann_return=0.18, ann_vol=0.12, ann_sharpe=1.5, max_dd=-0.08
        ),
        complexity_score=14.2,
        created_at=NOW - timedelta(days=3),
        tags=["momentum", "fx"],
        notes="Sample strategy derived from the architecture brief.",
    ),
    "def456": StrategyDetail(
        expr_hash="def456",
        expr='rank(zscore(feat("spread_eur_sek"))) > 0.5',
        metrics=StrategyMetrics(
            ann_return=0.11, ann_vol=0.09, ann_sharpe=1.2, max_dd=-0.06
        ),
        complexity_score=9.8,
        created_at=NOW - timedelta(days=7),
        tags=["mean-reversion"],
        notes="Placeholder mean-reversion strategy used for UI wiring.",
    ),
}

SAMPLE_EQUITY_CURVES: dict[str, EquityCurve] = {
    "abc123": EquityCurve(
        expr_hash="abc123",
        base_currency="SEK",
        dates=[NOW.date() - timedelta(days=i) for i in range(5)][::-1],
        equity=[1.0, 1.002, 1.01, 1.018, 1.025],
    ),
    "def456": EquityCurve(
        expr_hash="def456",
        base_currency="SEK",
        dates=[NOW.date() - timedelta(days=i) for i in range(5)][::-1],
        equity=[1.0, 0.998, 1.001, 1.003, 1.006],
    ),
}

SAMPLE_RETURNS: dict[str, DailyReturns] = {
    key: DailyReturns(
        expr_hash=curve.expr_hash,
        dates=curve.dates,
        returns=[round(v - 1, 4) for v in curve.equity],
    )
    for key, curve in SAMPLE_EQUITY_CURVES.items()
}

"""Legacy job/backtest placeholders removed in UI-only mode."""

SAMPLE_FEATURES = FeatureCatalogResponse(
    features=[
        FeatureDefinition(
            name="feat_price_sek", description="SEK close price", group="prices"
        ),
        FeatureDefinition(
            name="feat_volume", description="Daily traded volume", group="volume"
        ),
    ]
)

SAMPLE_PRIMITIVES = PrimitiveCatalogResponse(
    primitives=[
        PrimitiveDefinition(
            name="lag",
            description="Lag a feature by N periods",
            arity=2,
            category="transform",
        ),
        PrimitiveDefinition(
            name="zscore",
            description="Z-score normalisation",
            arity=1,
            category="transform",
        ),
        PrimitiveDefinition(
            name="clip",
            description="Clamp values within a range",
            arity=3,
            category="math",
        ),
    ]
)

# Broker sample positions removed (disabled broker)


# --------------------------- Helpers ---------------------------------------


def _get_manifest_path(settings: Settings) -> Path | None:
    """Return manifest.json path if artifacts_root configured, else None.

    We guard Path() construction because settings.artifacts_root may be None
    when the environment variable is not supplied; constructing Path(None)
    triggers type checker errors and runtime issues.
    """
    root = getattr(settings, "artifacts_root", None)
    if not root:
        return None
    return Path(root) / "manifest.json"


@router.get(
    "/health", response_model=HealthResponse, tags=["health"], summary="Health probe"
)
async def health(settings: SettingsDep) -> HealthResponse:
    """Return liveness information for the service."""

    return HealthResponse(
        status="ok", version=settings.version, git_commit=settings.git_commit
    )


@router.get(
    "/strategies",
    response_model=StrategyListResponse,
    tags=["strategies"],
    summary="List strategies",
)
async def list_strategies(
    settings: SettingsDep, limit: int = 20, offset: int = 0, order: str | None = None
) -> StrategyListResponse:
    # type: ignore[assignment]
    """Return strategy summaries from external engine or fallback sample."""
    if not settings.disable_adapter and adapter_available():
        payload = await fetch_strategies(limit=limit, offset=offset)
        # Local ordering if requested (adapter returns full slice only; we cannot re-fetch total sorted upstream yet)
        if order:
            # Apply ordering to current page only (documentation: adapter ordering limited)
            def _metric_val(s: StrategySummary, field: str):
                return getattr(s.metrics, field)

            def _apply_local(items: list[StrategySummary]):
                keys = [k.strip() for k in order.split(",") if k.strip()]
                for k in reversed(keys):
                    parts = k.split("_")
                    if len(parts) < 2:
                        field = k
                        direction = "asc"
                    else:
                        field = "_".join(parts[:-1])
                        direction = parts[-1]
                    reverse = direction.lower() == "desc"
                    if field in {"ann_return", "ann_vol", "ann_sharpe", "max_dd"}:
                        items.sort(
                            key=lambda s, f=field: _metric_val(s, f), reverse=reverse
                        )
                    elif field == "created_at":
                        items.sort(key=lambda s: s.created_at, reverse=reverse)
                    elif field in {"name", "expr_hash"}:
                        items.sort(key=lambda s: s.expr_hash.lower(), reverse=reverse)
                    elif field == "complexity_score":
                        items.sort(key=lambda s: s.complexity_score, reverse=reverse)

            _apply_local(payload.items)
            payload.order = order  # type: ignore[attr-defined]
        return payload
    # Config provider (quant_core_root/configs/*.json) path
    cfg_payload = load_config_strategies(limit, offset, order=order)
    if cfg_payload:
        return cfg_payload
    # JSON provider path
    json_payload = json_list_strategies(limit, offset)
    if json_payload:
        # Attach order + sorting client side for JSON sample (limited set)
        if order:
            from copy import deepcopy

            jp = deepcopy(json_payload)

            # Reuse local apply code
            def _metric_val(s: StrategySummary, field: str):
                return getattr(s.metrics, field)

            def _apply_local(items: list[StrategySummary]):
                keys = [k.strip() for k in order.split(",") if k.strip()]
                for k in reversed(keys):
                    parts = k.split("_")
                    if len(parts) < 2:
                        field = k
                        direction = "asc"
                    else:
                        field = "_".join(parts[:-1])
                        direction = parts[-1]
                    reverse = direction.lower() == "desc"
                    if field in {"ann_return", "ann_vol", "ann_sharpe", "max_dd"}:
                        items.sort(
                            key=lambda s, f=field: _metric_val(s, f), reverse=reverse
                        )
                    elif field == "created_at":
                        items.sort(key=lambda s: s.created_at, reverse=reverse)
                    elif field in {"name", "expr_hash"}:
                        items.sort(key=lambda s: s.expr_hash.lower(), reverse=reverse)
                    elif field == "complexity_score":
                        items.sort(key=lambda s: s.complexity_score, reverse=reverse)

            _apply_local(jp.items)
            jp.order = order  # type: ignore[attr-defined]
            return jp
        return json_payload
    # No real source found -> raise 503 with simple diagnostics
    raise HTTPException(
        status_code=503,
        detail={
            "error": "No strategy sources available",
            "adapter_available": adapter_available(),
            "config_root": getattr(settings, "quant_core_root", None),
            "strategies_root": settings.strategies_root,
            "hint": "Ensure QUANT_CORE_ROOT is set or provide strategies JSON/configs",
        },
    )


@router.get(
    "/strategies/{expr_hash}",
    response_model=StrategyDetail,
    tags=["strategies"],
    summary="Strategy detail",
)
async def get_strategy(expr_hash: str, settings: SettingsDep) -> StrategyDetail:
    # type: ignore[assignment]
    if not settings.disable_adapter and adapter_available():
        detail = await fetch_strategy_detail(expr_hash)
        if detail:
            return detail
    # Config provider
    cfg_detail = load_config_strategy_detail(expr_hash)
    if cfg_detail:
        return cfg_detail
    json_detail = json_strategy_detail(expr_hash)
    if json_detail:
        return json_detail
    raise HTTPException(
        status_code=404,
        detail={
            "error": "Strategy not found in any source",
            "expr_hash": expr_hash,
            "adapter_available": adapter_available(),
            "searched": [
                "adapter",
                "config_strategies",
                "json_provider",
            ],
        },
    )


@router.get(
    "/strategies/{expr_hash}/curve",
    response_model=EquityCurve,
    tags=["strategies"],
    summary="Strategy equity curve",
)
async def get_equity_curve(expr_hash: str, settings: SettingsDep) -> EquityCurve:
    # type: ignore[assignment]
    if not settings.disable_adapter and adapter_available():
        curve = await fetch_equity_curve(expr_hash)
        if curve:
            return curve
    json_curve = json_equity_curve(expr_hash)
    if json_curve:
        return json_curve
    curve = SAMPLE_EQUITY_CURVES.get(expr_hash)
    if curve:
        return curve
    # Synthetic fallback: deterministic pseudo equity series based on hash
    seed = int(hashlib.sha256(expr_hash.encode()).hexdigest()[:8], 16)
    days = 260
    # Map seed to drift/vol (annualised assumptions) then convert to daily
    rng_drift = ((seed >> 8) & 0xFFFF) / 0xFFFF  # 0..1
    rng_vol = ((seed >> 16) & 0xFFFF) / 0xFFFF
    ann_ret = 0.05 + 0.10 * (rng_drift - 0.5)  # ±5% around 5%
    ann_vol = 0.12 + 0.06 * (rng_vol - 0.5)  # ±3% around 12%
    daily_mu = ann_ret / 252
    daily_sigma = ann_vol / math.sqrt(252)
    eq = [1.0]
    # simple deterministic pseudo-random using linear congruential generator
    a = 1664525
    c = 1013904223
    m = 2**32
    x = seed
    for _ in range(days):
        x = (a * x + c) % m
        z = (x / m) * 2 - 1  # uniform -1..1
        r = daily_mu + daily_sigma * z * 0.7  # scale to keep moderate
        eq.append(eq[-1] * (1 + r))
    dates = [
        (NOW.date() - timedelta(days=days - i)).isoformat() for i in range(1, days + 1)
    ]
    synthetic = EquityCurve(
        expr_hash=expr_hash,
        base_currency="SEK",
        dates=dates,
        equity=[round(v, 6) for v in eq[1:]],
    )
    return synthetic


@router.get(
    "/strategies/{expr_hash}/returns",
    response_model=DailyReturns,
    tags=["strategies"],
    summary="Strategy daily returns",
)
async def get_daily_returns(expr_hash: str, settings: SettingsDep) -> DailyReturns:
    # type: ignore[assignment]
    if not settings.disable_adapter and adapter_available():
        curve = await fetch_equity_curve(expr_hash)
        if curve:
            eq = curve.equity
            returns = [round(eq[i] / eq[i - 1] - 1, 6) for i in range(1, len(eq))]
            return DailyReturns(
                expr_hash=expr_hash, dates=curve.dates[1:], returns=returns
            )
    json_ret = json_daily_returns(expr_hash)
    if json_ret:
        return json_ret
    payload = SAMPLE_RETURNS.get(expr_hash)
    if payload:
        return payload
    # Derive from synthetic equity fallback
    curve = await get_equity_curve(expr_hash, settings)
    if curve and len(curve.equity) > 1:
        eq = curve.equity
        returns = [round(eq[i] / eq[i - 1] - 1, 6) for i in range(1, len(eq))]
        return DailyReturns(expr_hash=expr_hash, dates=curve.dates[1:], returns=returns)
    raise HTTPException(status_code=404, detail="Returns not found")


@router.get(
    "/metrics/aggregate",
    response_model=AggregateMetrics,
    tags=["metrics"],
    summary="Aggregate metrics",
)
async def aggregate_metrics() -> AggregateMetrics:
    """Return aggregate Sharpe and drawdown distributions."""

    sharpes = [strategy.metrics.ann_sharpe for strategy in SAMPLE_STRATEGIES.values()]
    drawdowns = [strategy.metrics.max_dd for strategy in SAMPLE_STRATEGIES.values()]
    return AggregateMetrics(
        sharpe_distribution=sharpes,
        drawdown_distribution=drawdowns,
        as_of=NOW,
    )


@router.post("/backtest", tags=["backtest"], summary="Disabled backtest endpoint")
async def run_backtest_disabled() -> dict[str, str]:
    raise HTTPException(
        status_code=501, detail="Backtest functionality disabled in UI-only mode"
    )


@router.post("/jobs/train", tags=["jobs"], summary="Disabled training endpoint")
async def launch_training_job_disabled() -> dict[str, str]:
    raise HTTPException(
        status_code=501, detail="Training/jobs disabled in UI-only mode"
    )


@router.get("/jobs", tags=["jobs"], summary="Jobs disabled")
async def list_jobs_disabled() -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Jobs disabled in UI-only mode")


@router.get("/jobs/{job_id}", tags=["jobs"], summary="Job detail disabled")
async def get_job_disabled(job_id: str) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Jobs disabled in UI-only mode")


@router.get("/jobs/{job_id}/log", tags=["jobs"], summary="Job logs disabled")
async def get_job_log_disabled(job_id: str) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Jobs disabled in UI-only mode")


@router.websocket("/jobs/{job_id}/stream")
async def job_stream_disabled(
    websocket: WebSocket, job_id: str
) -> None:  # pragma: no cover - simple disable
    await websocket.accept()
    await websocket.send_json({"event": "error", "detail": "Job streaming disabled"})
    await websocket.close()


@router.get(
    "/config/features",
    response_model=FeatureCatalogResponse,
    tags=["config"],
    summary="Feature catalog",
)
async def feature_catalog(
    settings: SettingsDep,
) -> FeatureCatalogResponse:
    # type: ignore[assignment]
    if not settings.disable_adapter and adapter_available():
        catalog = await fetch_feature_catalog()
        if catalog:
            return catalog
    json_cat = json_feature_catalog()
    if json_cat:
        return json_cat
    return SAMPLE_FEATURES


@router.get(
    "/config/primitives",
    response_model=PrimitiveCatalogResponse,
    tags=["config"],
    summary="Primitive catalog",
)
async def primitive_catalog(
    settings: SettingsDep,
) -> PrimitiveCatalogResponse:
    # type: ignore[assignment]
    if not settings.disable_adapter and adapter_available():
        primitives = await fetch_primitive_catalog()
        if primitives:
            return primitives
    json_prims = json_primitive_catalog()
    if json_prims:
        return json_prims
    return SAMPLE_PRIMITIVES


@router.get("/panel/slice", tags=["panel"], summary="Panel slice")
async def panel_slice(
    start: str | None = None,
    end: str | None = None,
    tickers: str | None = None,
    limit_tickers: int | None = None,
) -> dict:
    """Return a lightweight slice of the curated panel for charting.

    Parameters
    ----------
    start, end: ISO date bounds (inclusive) as strings.
    tickers: Comma delimited ticker list.
    limit_tickers: Optional cap on distinct tickers (applied after filter).
    """
    settings = get_settings()
    ticker_list = (
        [t.strip() for t in tickers.split(",") if t.strip()] if tickers else None
    )
    if ticker_list and limit_tickers:
        ticker_list = ticker_list[:limit_tickers]
    payload = load_panel_slice(
        settings.data_root, start=start, end=end, tickers=ticker_list
    )
    return payload


# --------------------------- Strategy analysis -----------------------------
import re

_FEATURE_PATTERN = re.compile(r"feat\(\"([^\"]+)\"\)")


def _parse_expression(
    expr: str, primitive_names: list[str]
) -> tuple[list[str], list[str]]:
    """Extract features + primitive references from a DSL expression.

    This is a heuristic (regex) approach suitable for UI surfacing; it is not
    a full parser and may miss nested/obfuscated constructs, which is an
    acceptable trade-off for responsiveness and zero external dependencies.
    """
    features = sorted({m.group(1) for m in _FEATURE_PATTERN.finditer(expr)})
    primitives: set[str] = set()
    for name in primitive_names:
        if re.search(rf"\b{name}\b", expr):  # whole-word primitive reference
            primitives.add(name)
    return list(features), sorted(primitives)


@router.get(
    "/strategies/{expr_hash}/analysis",
    response_model=StrategyAnalysis,
    tags=["strategies"],
    summary="Static expression analysis",
)
async def strategy_analysis(expr_hash: str, settings: SettingsDep) -> StrategyAnalysis:
    """Return static analysis for the specified strategy expression.

    Provides feature + primitive usage plus simple size metrics.
    """
    # Resolve strategy detail
    if not settings.disable_adapter and adapter_available():
        detail = await fetch_strategy_detail(expr_hash)
    else:
        detail = None
    if detail is None:
        detail = json_strategy_detail(expr_hash) or SAMPLE_STRATEGIES.get(expr_hash)
    if detail is None:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Resolve primitive catalog
    if not settings.disable_adapter and adapter_available():
        prim_catalog = await fetch_primitive_catalog()
    else:
        prim_catalog = None
    if prim_catalog is None:
        prim_catalog = json_primitive_catalog() or SAMPLE_PRIMITIVES

    primitive_names = [p.name for p in prim_catalog.primitives]
    features_used, primitives_used = _parse_expression(detail.expr, primitive_names)
    expr_length = len(detail.expr)
    token_count = len(re.findall(r"[A-Za-z_]+|\d+|[()><=/*+\-]", detail.expr))
    return StrategyAnalysis(
        expr_hash=expr_hash,
        features_used=features_used,
        primitives_used=primitives_used,
        expr_length=expr_length,
        token_count=token_count,
    )


# --------------------------- Strategy analytics (drawdowns / rolling) -----


def _compute_drawdowns(dates: list[date], equity: list[float]):
    drawdowns: list[float] = []
    peak = equity[0] if equity else 1.0
    events: list[DrawdownEvent] = []
    current_start_idx: int | None = None
    trough_idx: int | None = None
    trough_dd = 0.0
    for i, v in enumerate(equity):
        if v > peak:
            # If exiting a drawdown, close event
            if current_start_idx is not None:
                # recovery date is dates[i] (new peak day)
                events.append(
                    DrawdownEvent(
                        start=dates[current_start_idx],
                        trough=dates[trough_idx],  # type: ignore[arg-type]
                        recovery=dates[i],
                        depth=trough_dd,
                        length=(i - current_start_idx),
                        days_to_trough=(trough_idx - current_start_idx),  # type: ignore[operator]
                    )
                )
                current_start_idx = None
                trough_idx = None
                trough_dd = 0.0
            peak = v
        dd = v / peak - 1.0
        drawdowns.append(dd)
        if dd < 0:
            if current_start_idx is None:
                current_start_idx = i
                trough_idx = i
                trough_dd = dd
            else:
                if dd < trough_dd:
                    trough_dd = dd
                    trough_idx = i
    # If still in drawdown at end, close incomplete event without recovery
    if current_start_idx is not None and trough_idx is not None:
        events.append(
            DrawdownEvent(
                start=dates[current_start_idx],
                trough=dates[trough_idx],
                recovery=None,
                depth=trough_dd,
                length=(len(equity) - current_start_idx - 1),
                days_to_trough=(trough_idx - current_start_idx),
            )
        )
    # Rank events by depth (most negative first)
    events.sort(key=lambda e: e.depth)
    return drawdowns, events


def _rolling_window(values: list[float], window: int, fn):
    out: list[float] = [float("nan")] * len(values)
    if window <= 1 or len(values) < window:
        return out
    for i in range(window - 1, len(values)):
        seg = values[i - window + 1 : i + 1]
        out[i] = fn(seg)
    return out


@router.get(
    "/strategies/{expr_hash}/analytics",
    response_model=StrategyAnalytics,
    tags=["strategies"],
    summary="Strategy analytics (drawdowns & rolling)",
)
async def strategy_analytics(expr_hash: str, settings: SettingsDep, window: int = 252, top: int = 5) -> StrategyAnalytics:  # type: ignore[assignment]
    if window <= 2:
        window = 252
    # Acquire equity curve (adapter / providers / sample)
    if not settings.disable_adapter and adapter_available():
        curve = await fetch_equity_curve(expr_hash)
    else:
        curve = None
    if curve is None:
        curve = json_equity_curve(expr_hash) or SAMPLE_EQUITY_CURVES.get(expr_hash)
    if curve is None:
        # use synthetic fallback (reuse logic from get_equity_curve)
        curve = await get_equity_curve(expr_hash, settings)
    dates = curve.dates
    equity = curve.equity
    if not equity:
        return StrategyAnalytics(expr_hash=expr_hash, as_of=NOW, window=window)
    drawdowns, events = _compute_drawdowns(dates, equity)
    top_events = events[:top]
    # Derive daily returns from equity for rolling metrics
    rets = []
    for i in range(1, len(equity)):
        r = equity[i] / equity[i - 1] - 1
        rets.append(r)
    # Pad to align lengths (first return is at index 1)
    daily = [float("nan")] + rets

    # Annualisation factor approximation (252 trading days)
    def annualised_return(seg):
        cum = 1.0
        for x in seg:
            cum *= 1 + x
        n = len(seg)
        # geometric annualised.
        return cum ** (252 / n) - 1 if n else float("nan")

    def annualised_vol(seg):
        import math

        if len(seg) < 2:
            return float("nan")
        mean = sum(seg) / len(seg)
        var = sum((x - mean) ** 2 for x in seg) / (len(seg) - 1)
        return (var**0.5) * (252**0.5)

    rolling_ret = _rolling_window(daily, window, annualised_return)
    rolling_vol = _rolling_window(daily, window, annualised_vol)
    rolling_sharpe = [
        (
            (r / v)
            if (i < len(rolling_ret) and i < len(rolling_vol) and v and v == v)
            else float("nan")
        )
        for i, (r, v) in enumerate(zip(rolling_ret, rolling_vol))
    ]
    # Monthly returns (geometric)
    from collections import defaultdict

    monthly_groups: dict[tuple[int, int], list[float]] = defaultdict(list)
    for d, r in zip(dates[1:], rets):  # align with returns indexing
        monthly_groups[(d.year, d.month)].append(r)
    monthly_returns: list[dict] = []
    for (y, m), seg in sorted(monthly_groups.items()):
        cum = 1.0
        for x in seg:
            cum *= 1 + x
        monthly_returns.append({"year": y, "month": m, "return": cum - 1})

    # Return histogram on daily returns (exclude first NaN-like position)
    hist_bins: list[dict] = []
    hist_meta: dict | None = None
    if rets:
        vals = rets[:]  # copy
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        if n > 1:
            import math

            q1 = vals_sorted[int(0.25 * (n - 1))]
            q3 = vals_sorted[int(0.75 * (n - 1))]
            iqr = q3 - q1
            bin_width = (2 * iqr / (n ** (1 / 3))) if iqr > 0 else 0
            if not bin_width or bin_width <= 0:
                # fallback width ~0.25% absolute
                bin_width = 0.0025
            data_min = min(vals_sorted)
            data_max = max(vals_sorted)
            span = data_max - data_min or 1e-9
            bins_calc = max(5, min(80, int(span / bin_width)))
            bucket_size = span / bins_calc if bins_calc else span
            # Build bins
            counts = [0] * bins_calc
            for v in vals_sorted:
                idx = int((v - data_min) / span * bins_calc)
                if idx == bins_calc:  # right edge inclusion
                    idx -= 1
                counts[idx] += 1
            for i, c in enumerate(counts):
                start = data_min + (i / bins_calc) * span
                end = data_min + ((i + 1) / bins_calc) * span
                hist_bins.append({"start": start, "end": end, "count": c})
            hist_meta = {
                "min": data_min,
                "max": data_max,
                "bucket_size": bucket_size,
                "total": n,
            }

    # Distribution summary statistics over daily returns (rets)
    dist_stats: dict | None = None
    if rets:
        import math

        n_rets = len(rets)
        mean = sum(rets) / n_rets
        var = sum((x - mean) ** 2 for x in rets) / (n_rets - 1) if n_rets > 1 else 0.0
        std = math.sqrt(var)
        # higher moments (sample-based)
        if std > 0:
            skew = (
                sum(((x - mean) / std) ** 3 for x in rets) * (n_rets / ((n_rets - 1)))
                if n_rets > 2
                else float("nan")
            )
            kurt = (
                sum(((x - mean) / std) ** 4 for x in rets) * (n_rets / ((n_rets - 1)))
                if n_rets > 3
                else float("nan")
            ) - 3
        else:
            skew = float("nan")
            kurt = float("nan")
        sorted_rets = sorted(rets)

        def _pct(p: float):
            if n_rets == 1:
                return sorted_rets[0]
            k = (n_rets - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return sorted_rets[int(k)]
            d0 = sorted_rets[f] * (c - k)
            d1 = sorted_rets[c] * (k - f)
            return d0 + d1

        p5 = _pct(0.05)
        p50 = _pct(0.50)
        p95 = _pct(0.95)
        neg = [x for x in rets if x < 0]
        negative_share = len(neg) / n_rets
        downside_dev = 0.0
        if neg:
            downside_dev = (sum(x * x for x in neg) / len(neg)) ** 0.5
        # Sortino (annualised return / annualised downside volatility)
        # Annualised return approx using mean * 252 (simple) vs geometric; we use mean*252 for speed here.
        ann_ret_simple = mean * 252
        ann_downside_vol = downside_dev * (252**0.5)
        sortino = (
            ann_ret_simple / ann_downside_vol if ann_downside_vol else float("nan")
        )
        dist_stats = {
            "mean": mean,
            "std": std,
            "skew": skew,
            "kurtosis": kurt,
            "p5": p5,
            "p50": p50,
            "p95": p95,
            "count": n_rets,
            "negative_share": negative_share,
            "downside_dev": downside_dev,
            "sortino": sortino,
        }

    return StrategyAnalytics(
        expr_hash=expr_hash,
        as_of=NOW,
        dd_dates=dates,
        drawdowns=drawdowns,
        top_drawdowns=top_events,
        window=window,
        rolling_return=rolling_ret,
        rolling_vol=rolling_vol,
        rolling_sharpe=rolling_sharpe,
        monthly_returns=monthly_returns,
        return_histogram=({"bins": hist_bins, **hist_meta} if hist_meta else None),
        dist_stats=dist_stats,
    )


# --------------------------- Debug / Source probe ---------------------------


@router.get("/debug/source", tags=["debug"], summary="Active data source diagnostics")
async def debug_source() -> dict:
    """Return a diagnostic snapshot describing where strategy data is coming
    from (adapter / config / json / none) plus key environment-derived paths.

    This is useful when .env loading is in doubt; it allows the UI or a user
    to confirm which layer provided (or failed to provide) strategy data.
    """
    settings = get_settings()
    # Evaluate availability in precedence order used by list_strategies
    source = "none"
    adapter_ok = adapter_available() and not settings.disable_adapter
    cfg_ok = bool(load_config_strategies(limit=1, offset=0))
    json_ok = bool(json_list_strategies(limit=1, offset=0))
    if adapter_ok:
        source = "adapter"
    elif cfg_ok:
        source = "config"
    elif json_ok:
        source = "json"
    return {
        "source": source,
        "adapter_available": adapter_ok,
        "config_available": cfg_ok,
        "json_available": json_ok,
        "env": {
            "quant_core_root": settings.quant_core_root,
            "strategies_root": settings.strategies_root,
            "catalog_root": settings.catalog_root,
            "curves_root": settings.curves_root,
            "artifacts_root": settings.artifacts_root,
            "disable_adapter": settings.disable_adapter,
        },
        "hint": "Ensure .env is in the working directory where uvicorn is started or export QUANT_* vars before launch.",
    }


# --------------------------- Artifacts passthrough ---------------------------


@router.get(
    "/artifacts/manifest", tags=["artifacts"], summary="Raw manifest.json contents"
)
async def artifacts_manifest() -> dict:
    settings = get_settings()
    manifest_path = _get_manifest_path(settings)
    if manifest_path is None:
        raise HTTPException(status_code=404, detail="artifacts_root not configured")
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest.json not found")
    return load_manifest(manifest_path)


def _filter_entries(manifest: dict, kind: str) -> list[dict]:
    entries = manifest.get("entries", [])
    return [e for e in entries if e.get("kind") == kind]


# --------------------------- Catalog aggregation ----------------------------


@router.get(
    "/catalog/manifest",
    response_model=CatalogManifest,
    tags=["catalog"],
    summary="Aggregated catalog manifest",
)
async def catalog_manifest(settings: SettingsDep) -> CatalogManifest:
    """Return a unified catalog combining features, primitives, strategy tag
    frequencies, artifact kind counts and dataset listing.

    Falls back to in-memory samples if adapter/artifacts are unavailable.
    """
    # Features & primitives (adapter first, else samples)
    if adapter_available():
        feature_catalog = await fetch_feature_catalog() or SAMPLE_FEATURES
        primitive_catalog = await fetch_primitive_catalog() or SAMPLE_PRIMITIVES
        strategies_payload = await fetch_strategies(limit=500, offset=0)
        strategies = (
            strategies_payload.items
            if strategies_payload
            else list(SAMPLE_STRATEGIES.values())
        )
    else:
        feature_catalog = SAMPLE_FEATURES
        primitive_catalog = SAMPLE_PRIMITIVES
        strategies = list(SAMPLE_STRATEGIES.values())

    # Strategy tag stats
    tag_counter: Counter[str] = Counter()
    for s in strategies:
        if getattr(s, "tags", None):
            tag_counter.update(s.tags)  # type: ignore[arg-type]
    tag_stats = [
        CatalogStrategyTagStat(tag=k, count=v) for k, v in tag_counter.most_common()
    ]

    # Artifacts manifest & dataset extraction
    manifest_path = _get_manifest_path(settings)
    artifact_counts = CatalogArtifactCounts()
    datasets: list[CatalogDatasetEntry] = []

    def _parse_created(value: str | None) -> datetime:
        if not value:
            return NOW
        v = value.strip()
        if v.endswith("Z"):
            v = v[:-1]
        try:
            return datetime.fromisoformat(v)
        except Exception:
            return NOW

    if manifest_path and manifest_path.exists():
        m = load_manifest(manifest_path)
        entries = m.get("entries", [])
        kind_counter: Counter[str] = Counter(e.get("kind") for e in entries)
        artifact_counts = CatalogArtifactCounts(
            models=kind_counter.get("model", 0),
            reports=kind_counter.get("report", 0),
            signals=kind_counter.get("signal", 0),
            logs=kind_counter.get("log", 0),
            datasets=kind_counter.get("dataset", 0),
            strategies=kind_counter.get("strategie", 0),  # backward compat
        )
        for e in entries:
            if e.get("kind") == "dataset":
                datasets.append(
                    CatalogDatasetEntry(
                        file=e.get("file"),
                        size=e.get("size", 0),
                        created=_parse_created(e.get("created")),
                    )
                )

    return CatalogManifest(
        generated_at=NOW,
        git_commit=settings.git_commit,
        data_version=settings.data_version,
        feature_count=len(feature_catalog.features),
        primitive_count=len(primitive_catalog.primitives),
        features=feature_catalog.features,
        primitives=primitive_catalog.primitives,
        strategy_tags=tag_stats,
        artifacts=artifact_counts,
        datasets=datasets,
        version=1,
    )


@router.get("/artifacts/models", tags=["artifacts"], summary="Model artifact list")
async def list_models() -> dict:
    settings = get_settings()
    manifest_path = _get_manifest_path(settings)
    if manifest_path is None:
        raise HTTPException(status_code=404, detail="artifacts_root not configured")
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest.json not found")
    m = load_manifest(manifest_path)
    return {"models": _filter_entries(m, "model")}


@router.get("/artifacts/reports", tags=["artifacts"], summary="Report artifact list")
async def list_reports() -> dict:
    settings = get_settings()
    manifest_path = _get_manifest_path(settings)
    if manifest_path is None:
        raise HTTPException(status_code=404, detail="artifacts_root not configured")
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest.json not found")
    m = load_manifest(manifest_path)
    return {"reports": _filter_entries(m, "report")}


@router.get("/artifacts/signals", tags=["artifacts"], summary="Signal artifact list")
async def list_signals() -> dict:
    settings = get_settings()
    manifest_path = _get_manifest_path(settings)
    if manifest_path is None:
        raise HTTPException(status_code=404, detail="artifacts_root not configured")
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest.json not found")
    m = load_manifest(manifest_path)
    return {"signals": _filter_entries(m, "signal")}


@router.get("/artifacts/logs", tags=["artifacts"], summary="Log artifact list")
async def list_logs() -> dict:
    settings = get_settings()
    manifest_path = _get_manifest_path(settings)
    if manifest_path is None:
        raise HTTPException(status_code=404, detail="artifacts_root not configured")
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest.json not found")
    m = load_manifest(manifest_path)
    return {"logs": _filter_entries(m, "log")}


@router.get("/artifacts/datasets", tags=["artifacts"], summary="Dataset artifact list")
async def list_datasets() -> dict:
    settings = get_settings()
    manifest_path = _get_manifest_path(settings)
    if manifest_path is None:
        raise HTTPException(status_code=404, detail="artifacts_root not configured")
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest.json not found")
    m = load_manifest(manifest_path)
    return {"datasets": _filter_entries(m, "dataset")}


@router.get(
    "/artifacts/strategies", tags=["artifacts"], summary="Strategy artifact list"
)
async def list_strategy_artifacts() -> dict:
    settings = get_settings()
    manifest_path = _get_manifest_path(settings)
    if manifest_path is None:
        raise HTTPException(status_code=404, detail="artifacts_root not configured")
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest.json not found")
    m = load_manifest(manifest_path)
    return {"strategies": _filter_entries(m, "strategie")}


"""Broker endpoints removed in UI-only mode."""


@router.post("/broker/orders", tags=["broker"], summary="Broker disabled")
async def place_order_disabled() -> dict[str, str]:
    raise HTTPException(
        status_code=501, detail="Broker functionality disabled in UI-only mode"
    )
