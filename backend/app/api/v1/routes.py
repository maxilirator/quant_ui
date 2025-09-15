"""Version 1 API routes."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket

from app.core.config import Settings, get_settings

from .schemas import (
    AggregateMetrics,
    BacktestRequest,
    BacktestResponse,
    BrokerPosition,
    DailyReturns,
    EquityCurve,
    FeatureCatalogResponse,
    FeatureDefinition,
    HealthResponse,
    JobListResponse,
    JobLogEntry,
    JobLogResponse,
    JobStatus,
    OrderRequest,
    OrderResponse,
    PrimitiveCatalogResponse,
    PrimitiveDefinition,
    StrategyDetail,
    StrategyListResponse,
    StrategyMetrics,
    StrategySummary,
    TrainJobRequest,
)

router = APIRouter()


SettingsDep = Annotated[Settings, Depends(get_settings)]


NOW = datetime.now(UTC)

SAMPLE_STRATEGIES: dict[str, StrategyDetail] = {
    "abc123": StrategyDetail(
        expr_hash="abc123",
        expr="clip(feat(\"c_sek\")/lag(feat(\"c_sek\"),1)-1)",
        metrics=StrategyMetrics(ann_return=0.18, ann_vol=0.12, ann_sharpe=1.5, max_dd=-0.08),
        complexity_score=14.2,
        created_at=NOW - timedelta(days=3),
        tags=["momentum", "fx"],
        notes="Sample strategy derived from the architecture brief.",
    ),
    "def456": StrategyDetail(
        expr_hash="def456",
        expr="rank(zscore(feat(\"spread_eur_sek\"))) > 0.5",
        metrics=StrategyMetrics(ann_return=0.11, ann_vol=0.09, ann_sharpe=1.2, max_dd=-0.06),
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
    key: DailyReturns(expr_hash=curve.expr_hash, dates=curve.dates, returns=[round(v - 1, 4) for v in curve.equity])
    for key, curve in SAMPLE_EQUITY_CURVES.items()
}

SAMPLE_JOBS: dict[str, JobStatus] = {
    "job_train_001": JobStatus(
        job_id="job_train_001",
        type="train",
        status="completed",
        progress=1.0,
        processed=50,
        submitted_at=NOW - timedelta(hours=5),
        started_at=NOW - timedelta(hours=4, minutes=45),
        completed_at=NOW - timedelta(hours=4, minutes=15),
        summary=SAMPLE_STRATEGIES["abc123"],
    ),
    "job_bt_001": JobStatus(
        job_id="job_bt_001",
        type="backtest",
        status="running",
        progress=0.42,
        processed=21,
        submitted_at=NOW - timedelta(minutes=45),
        started_at=NOW - timedelta(minutes=40),
        completed_at=None,
        summary=None,
    ),
}

SAMPLE_JOB_LOGS: dict[str, list[JobLogEntry]] = {
    "job_train_001": [
        JobLogEntry(
            ts=NOW - timedelta(hours=4, minutes=45),
            level="INFO",
            message="job_start",
            context={"type": "train"},
        ),
        JobLogEntry(
            ts=NOW - timedelta(hours=4, minutes=20),
            level="INFO",
            message="expr_evaluated",
            context={"processed": 25, "total": 50},
        ),
        JobLogEntry(
            ts=NOW - timedelta(hours=4, minutes=15),
            level="INFO",
            message="job_complete",
            context={"result": "success"},
        ),
    ]
}

SAMPLE_FEATURES = FeatureCatalogResponse(
    features=[
        FeatureDefinition(name="feat_price_sek", description="SEK close price", group="prices"),
        FeatureDefinition(name="feat_volume", description="Daily traded volume", group="volume"),
    ]
)

SAMPLE_PRIMITIVES = PrimitiveCatalogResponse(
    primitives=[
        PrimitiveDefinition(name="lag", description="Lag a feature by N periods", arity=2, category="transform"),
        PrimitiveDefinition(name="zscore", description="Z-score normalisation", arity=1, category="transform"),
        PrimitiveDefinition(name="clip", description="Clamp values within a range", arity=3, category="math"),
    ]
)

SAMPLE_POSITIONS = [
    BrokerPosition(symbol="EURSEK", quantity=1_000_000, avg_price=11.2, market_value=1_000_000 * 11.35, currency="SEK"),
    BrokerPosition(symbol="USDSEK", quantity=-500_000, avg_price=10.4, market_value=-500_000 * 10.25, currency="SEK"),
]


@router.get("/health", response_model=HealthResponse, tags=["health"], summary="Health probe")
async def health(settings: SettingsDep) -> HealthResponse:
    """Return liveness information for the service."""

    return HealthResponse(status="ok", version=settings.version, git_commit=settings.git_commit)


@router.get(
    "/strategies",
    response_model=StrategyListResponse,
    tags=["strategies"],
    summary="List strategies",
)
async def list_strategies(limit: int = 20, offset: int = 0) -> StrategyListResponse:
    """Return a paginated list of strategy summaries."""

    items = list(SAMPLE_STRATEGIES.values())
    sliced = items[offset : offset + limit]
    return StrategyListResponse(items=sliced, total=len(items), limit=limit, offset=offset)


@router.get(
    "/strategies/{expr_hash}",
    response_model=StrategyDetail,
    tags=["strategies"],
    summary="Strategy detail",
)
async def get_strategy(expr_hash: str) -> StrategyDetail:
    """Return metadata and metrics for a specific strategy."""

    strategy = SAMPLE_STRATEGIES.get(expr_hash)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.get(
    "/strategies/{expr_hash}/curve",
    response_model=EquityCurve,
    tags=["strategies"],
    summary="Strategy equity curve",
)
async def get_equity_curve(expr_hash: str) -> EquityCurve:
    """Return an equity curve for the requested strategy."""

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
async def get_daily_returns(expr_hash: str) -> DailyReturns:
    """Return the raw returns for the requested strategy."""

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


@router.post(
    "/backtest",
    response_model=BacktestResponse,
    tags=["backtest"],
    summary="Launch an ad-hoc backtest",
)
async def run_backtest(request: BacktestRequest) -> BacktestResponse:
    """Accept a backtest request and return a stub response."""

    job_id = f"job_bt_{uuid4().hex[:8]}"
    summary = StrategySummary(
        expr_hash=uuid4().hex[:6],
        expr=request.expr,
        metrics=StrategyMetrics(ann_return=0.05, ann_vol=0.08, ann_sharpe=0.9, max_dd=-0.12),
        complexity_score=7.5,
        created_at=NOW,
    )
    job = JobStatus(
        job_id=job_id,
        type="backtest",
        status="queued",
        progress=0.0,
        processed=0,
        submitted_at=NOW,
        started_at=None,
        completed_at=None,
        summary=summary,
    )
    SAMPLE_JOBS[job_id] = job
    SAMPLE_JOB_LOGS[job_id] = [
        JobLogEntry(ts=NOW, level="INFO", message="job_queued", context={"expr": request.expr})
    ]
    return BacktestResponse(job_id=job_id, status="queued", result=summary)


@router.post(
    "/jobs/train",
    response_model=JobStatus,
    tags=["jobs"],
    summary="Launch a training job",
)
async def launch_training_job(request: TrainJobRequest) -> JobStatus:
    """Accept a training job request and return the queued job."""

    job_id = f"job_train_{uuid4().hex[:8]}"
    job = JobStatus(
        job_id=job_id,
        type="train",
        status="queued",
        progress=0.0,
        processed=0,
        submitted_at=NOW,
        started_at=None,
        completed_at=None,
        summary=None,
    )
    SAMPLE_JOBS[job_id] = job
    SAMPLE_JOB_LOGS[job_id] = [
        JobLogEntry(ts=NOW, level="INFO", message="job_queued", context={"n": request.n})
    ]
    return job


@router.get("/jobs", response_model=JobListResponse, tags=["jobs"], summary="List jobs")
async def list_jobs() -> JobListResponse:
    """Return the tracked jobs."""

    items = sorted(SAMPLE_JOBS.values(), key=lambda job: job.submitted_at, reverse=True)
    return JobListResponse(items=items, total=len(items))


@router.get("/jobs/{job_id}", response_model=JobStatus, tags=["jobs"], summary="Job detail")
async def get_job(job_id: str) -> JobStatus:
    """Return a specific job."""

    job = SAMPLE_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get(
    "/jobs/{job_id}/log",
    response_model=JobLogResponse,
    tags=["jobs"],
    summary="Job logs",
)
async def get_job_log(job_id: str) -> JobLogResponse:
    """Return accumulated logs for a job."""

    entries = SAMPLE_JOB_LOGS.get(job_id)
    if entries is None:
        raise HTTPException(status_code=404, detail="Job log not found")
    return JobLogResponse(job_id=job_id, entries=entries)


@router.websocket("/jobs/{job_id}/stream")
async def job_stream(websocket: WebSocket, job_id: str) -> None:
    """Serve a minimal websocket that streams a job snapshot."""

    await websocket.accept()
    job = SAMPLE_JOBS.get(job_id)
    if job is None:
        await websocket.send_json({"event": "error", "detail": "Job not found"})
    else:
        await websocket.send_json({"event": "snapshot", "job": job.model_dump(mode="json")})
    await websocket.close()


@router.get(
    "/config/features",
    response_model=FeatureCatalogResponse,
    tags=["config"],
    summary="Feature catalog",
)
async def feature_catalog() -> FeatureCatalogResponse:
    """Return the DSL feature catalog."""

    return SAMPLE_FEATURES


@router.get(
    "/config/primitives",
    response_model=PrimitiveCatalogResponse,
    tags=["config"],
    summary="Primitive catalog",
)
async def primitive_catalog() -> PrimitiveCatalogResponse:
    """Return DSL primitive metadata."""

    return SAMPLE_PRIMITIVES


@router.get(
    "/broker/positions",
    response_model=list[BrokerPosition],
    tags=["broker"],
    summary="Broker positions",
)
async def broker_positions() -> list[BrokerPosition]:
    """Return dummy broker positions."""

    return SAMPLE_POSITIONS


@router.post(
    "/broker/orders",
    response_model=OrderResponse,
    tags=["broker"],
    summary="Submit broker order",
)
async def place_order(payload: OrderRequest) -> OrderResponse:
    """Accept an order and respond with an acknowledgement."""

    status: str = "accepted" if payload.qty > 0 else "rejected"
    order = OrderResponse(
        order_id=f"ord_{uuid4().hex[:10]}",
        status=status,
        submitted_at=datetime.now(UTC),
        symbol=payload.symbol,
        side=payload.side,
        qty=payload.qty,
        order_type=payload.order_type,
    )
    return order
