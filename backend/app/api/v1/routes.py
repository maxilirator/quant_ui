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
    if not curve:
        raise HTTPException(status_code=404, detail="Equity curve not found")
    return curve


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
    if not payload:
        raise HTTPException(status_code=404, detail="Returns not found")
    return payload


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
