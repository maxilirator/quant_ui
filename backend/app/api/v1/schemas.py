"""Pydantic models describing the public API surface."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StrategyMetrics(BaseModel):
    """Core metrics exposed for a strategy."""

    ann_return: float = Field(
        ..., description="Annualised return expressed as a decimal fraction."
    )
    ann_vol: float = Field(
        ..., description="Annualised volatility expressed as a decimal fraction."
    )
    ann_sharpe: float = Field(..., description="Annualised Sharpe ratio.")
    max_dd: float = Field(
        ..., description="Maximum drawdown experienced by the strategy."
    )


class StrategySummary(BaseModel):
    """Minimal representation of a trading strategy."""

    expr_hash: str
    expr: str
    metrics: StrategyMetrics
    complexity_score: float
    created_at: datetime


class StrategyDetail(StrategySummary):
    """Extended strategy metadata for the detail route."""

    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class StrategyListResponse(BaseModel):
    """Paginated list response for strategies."""

    items: list[StrategySummary]
    total: int
    limit: int
    offset: int
    order: str | None = Field(
        default=None,
        description="Ordering applied to the collection (e.g. 'ann_return_desc,ann_sharpe_desc').",
    )


class EquityCurve(BaseModel):
    """Equity curve payload down-sampled for charting."""

    expr_hash: str
    base_currency: str
    dates: list[date]
    equity: list[float]


class DailyReturns(BaseModel):
    """Daily returns emitted by a strategy."""

    expr_hash: str
    dates: list[date]
    returns: list[float]


class AggregateMetrics(BaseModel):
    """Distribution level metrics for dashboards."""

    sharpe_distribution: list[float]
    drawdown_distribution: list[float]
    as_of: datetime


class BacktestRequest(BaseModel):
    """Body for an ad-hoc backtest request."""

    expr: str
    seed: int | None = None
    persist: bool = False


class BacktestResponse(BaseModel):
    """Response describing the submitted backtest."""

    job_id: str | None = None
    status: Literal["queued", "completed", "failed"]
    result: StrategySummary | None = None


class JobParams(BaseModel):
    """Configuration namespace for training jobs."""

    cap: float | None = None
    max_lev: float | None = Field(default=None, alias="max_lev")
    execution_lag: int | None = None
    smooth_ema: float | None = None
    limit_score: float | None = None

    model_config = {"populate_by_name": True}


class TrainJobRequest(BaseModel):
    """Request body for launching training jobs."""

    n: int
    seed: int | None = None
    workers: int | None = None
    params: JobParams


class JobStatus(BaseModel):
    """Lifecycle representation for a job."""

    job_id: str
    type: Literal["train", "backtest"]
    status: Literal["queued", "running", "completed", "failed"]
    progress: float | None = None
    processed: int | None = None
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    summary: StrategySummary | None = None


class JobListResponse(BaseModel):
    """Envelope for paginated job responses."""

    items: list[JobStatus]
    total: int


class JobLogEntry(BaseModel):
    """Structured log line emitted by a worker."""

    ts: datetime
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class JobLogResponse(BaseModel):
    """Log payload for a job."""

    job_id: str
    entries: list[JobLogEntry]


class FeatureDefinition(BaseModel):
    """Describes a single feature exposed to the DSL."""

    name: str
    description: str
    group: str


class FeatureCatalogResponse(BaseModel):
    """Response containing feature definitions."""

    features: list[FeatureDefinition]


class PrimitiveDefinition(BaseModel):
    """Describes a primitive operation in the DSL."""

    name: str
    description: str
    arity: int
    category: str


class PrimitiveCatalogResponse(BaseModel):
    """Response for DSL primitives."""

    primitives: list[PrimitiveDefinition]


class BrokerPosition(BaseModel):
    """Summary of a broker position used in the UI."""

    symbol: str
    quantity: float
    avg_price: float
    market_value: float
    currency: str


class OrderRequest(BaseModel):
    """Payload for placing orders via the stub broker."""

    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    order_type: Literal["mkt", "lmt"] = "mkt"
    limit_price: float | None = None


class OrderResponse(BaseModel):
    """Acknowledgement returned by the broker stub."""

    order_id: str
    status: Literal["accepted", "rejected"]
    submitted_at: datetime
    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    order_type: Literal["mkt", "lmt"]


class HealthResponse(BaseModel):
    """Basic health check payload."""

    status: Literal["ok", "degraded"]
    version: str
    git_commit: str | None = None


# ---------------- Catalog Aggregation (optional) ----------------


class CatalogArtifactCounts(BaseModel):
    models: int = 0
    reports: int = 0
    signals: int = 0
    logs: int = 0
    datasets: int = 0
    strategies: int = 0


class CatalogStrategyTagStat(BaseModel):
    tag: str
    count: int


class CatalogDatasetEntry(BaseModel):
    file: str
    size: int
    created: datetime


class CatalogManifest(BaseModel):
    generated_at: datetime
    git_commit: str | None = None
    data_version: str | None = None
    feature_count: int
    primitive_count: int
    features: list[FeatureDefinition]
    primitives: list[PrimitiveDefinition]
    strategy_tags: list[CatalogStrategyTagStat]
    artifacts: CatalogArtifactCounts
    datasets: list[CatalogDatasetEntry] = Field(default_factory=list)
    version: int = 1


# ---------------- Strategy Expression Analysis ----------------


class StrategyAnalysis(BaseModel):
    """Lightweight static analysis of a strategy expression.

    Provides introspection for UI components: which features and primitives
    are referenced, along with simple size metrics. This is intentionally
    heuristic (string / regex based) and does not perform full DSL parsing.
    """

    expr_hash: str
    features_used: list[str] = Field(default_factory=list)
    primitives_used: list[str] = Field(default_factory=list)
    expr_length: int
    token_count: int


# ---------------- Strategy Analytics (drawdowns & rolling) ---------------


class DrawdownEvent(BaseModel):
    """Single drawdown episode from peak to trough (and optional recovery)."""

    start: date
    trough: date
    recovery: date | None = None
    depth: float = Field(..., description="Depth of drawdown (negative fraction).")
    length: int = Field(
        ...,
        description="Total days from start to recovery (or last observation if unrecovered).",
    )
    days_to_trough: int


class StrategyAnalytics(BaseModel):
    """Aggregated time-series analytics for a strategy.

    Provided as a single payload to minimise round trips.
    All series are aligned by date index where applicable.
    """

    expr_hash: str
    as_of: datetime
    # Drawdown series (same length as equity if available)
    dd_dates: list[date] = Field(default_factory=list)
    drawdowns: list[float] = Field(
        default_factory=list,
        description="Per-date drawdown values (negative fractions).",
    )
    top_drawdowns: list[DrawdownEvent] = Field(default_factory=list)
    # Rolling metrics (annualised where applicable) using a 252-day window default
    window: int | None = None
    rolling_return: list[float] = Field(
        default_factory=list, description="Trailing annualised return."
    )
    rolling_vol: list[float] = Field(
        default_factory=list, description="Trailing annualised volatility."
    )
    rolling_sharpe: list[float] = Field(
        default_factory=list, description="Trailing annualised Sharpe (return / vol)."
    )
    # Phase 2 additions
    monthly_returns: list[dict] = Field(
        default_factory=list,
        description="List of {year, month, return} (geometric monthly returns).",
    )
    return_histogram: dict | None = Field(
        default=None,
        description="Histogram of daily returns: {bins:[{start,end,count}], min,max,bucket_size,total}.",
    )
    # Phase 3 additions: distribution summary statistics
    dist_stats: dict | None = Field(
        default=None,
        description=(
            "Distribution statistics over daily returns: {mean,std,skew,kurtosis,p5,p50,p95,count,negative_share,downside_dev,sortino}."
        ),
    )


__all__ = [
    "AggregateMetrics",
    "BacktestRequest",
    "BacktestResponse",
    "BrokerPosition",
    "CatalogArtifactCounts",
    "CatalogDatasetEntry",
    "CatalogManifest",
    "CatalogStrategyTagStat",
    "DailyReturns",
    "EquityCurve",
    "FeatureCatalogResponse",
    "FeatureDefinition",
    "HealthResponse",
    "JobListResponse",
    "JobLogEntry",
    "JobLogResponse",
    "JobParams",
    "JobStatus",
    "OrderRequest",
    "OrderResponse",
    "PrimitiveCatalogResponse",
    "PrimitiveDefinition",
    "StrategyDetail",
    "StrategyListResponse",
    "StrategyMetrics",
    "StrategySummary",
    "TrainJobRequest",
    "StrategyAnalysis",
]
