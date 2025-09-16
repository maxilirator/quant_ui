export interface StrategyMetrics {
  ann_return: number;
  ann_vol: number;
  ann_sharpe: number;
  max_dd: number;
}

export interface StrategySummary {
  expr_hash: string;
  expr: string;
  metrics: StrategyMetrics;
  complexity_score: number;
  created_at: string;
  tags?: string[];
  notes?: string | null;
}

export interface StrategyListResponse {
  items: StrategySummary[];
  total: number;
  limit: number;
  offset: number;
  order?: string | null;
}

export interface EquityCurve {
  expr_hash: string;
  base_currency: string;
  dates: string[];
  equity: number[];
}

// Static analysis of a strategy expression (features + primitives + size metrics)
export interface StrategyAnalysis {
  expr_hash: string;
  features_used: string[];
  primitives_used: string[];
  expr_length: number;
  token_count: number;
}

export interface DailyReturns {
  expr_hash: string;
  dates: string[];
  returns: number[];
}

export interface AggregateMetrics {
  sharpe_distribution: number[];
  drawdown_distribution: number[];
  as_of: string;
}

// Deprecated (UI now read-only): backtest & job related types retained for legacy imports.
// Consider removing once all references are purged.
export interface BacktestRequest { expr: string; seed?: number; persist?: boolean } // deprecated
export interface BacktestResponse { job_id: string | null; status: 'queued' | 'completed' | 'failed'; result?: StrategySummary | null } // deprecated

export interface JobParams { cap?: number | null; max_lev?: number | null; execution_lag?: number | null; smooth_ema?: number | null; limit_score?: number | null } // deprecated

export interface TrainJobRequest { n: number; seed?: number; workers?: number; params: JobParams } // deprecated

export interface JobStatus { job_id: string; type: 'train' | 'backtest'; status: 'queued' | 'running' | 'completed' | 'failed'; progress?: number | null; processed?: number | null; submitted_at: string; started_at?: string | null; completed_at?: string | null; summary?: StrategySummary | null } // deprecated

export interface JobListResponse { items: JobStatus[]; total: number } // deprecated

export interface JobLogEntry { ts: string; level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'; message: string; context?: Record<string, unknown> } // deprecated

export interface JobLogResponse { job_id: string; entries: JobLogEntry[] } // deprecated

export interface FeatureDefinition {
  name: string;
  description: string;
  group: string;
}

export interface FeatureCatalogResponse {
  features: FeatureDefinition[];
}

export interface PrimitiveDefinition {
  name: string;
  description: string;
  arity: number;
  category: string;
}

export interface PrimitiveCatalogResponse {
  primitives: PrimitiveDefinition[];
}

export interface BrokerPosition { symbol: string; quantity: number; avg_price: number; market_value: number; currency: string } // deprecated

export interface OrderRequest { symbol: string; side: 'buy' | 'sell'; qty: number; order_type?: 'mkt' | 'lmt'; limit_price?: number | null } // deprecated

export interface OrderResponse { order_id: string; status: 'accepted' | 'rejected'; submitted_at: string; symbol: string; side: 'buy' | 'sell'; qty: number; order_type: 'mkt' | 'lmt' } // deprecated

export interface HealthResponse {
  status: 'ok' | 'degraded';
  version: string;
  git_commit?: string | null;
}

// New artifact & panel slice types
export interface ArtifactEntry { file: string; sha256: string; size: number; created: string; kind: string }
export interface ArtifactManifest { generated_at: string; git_commit?: string | null; data_version?: string | null; entries: ArtifactEntry[]; version: number }
export interface PanelSliceResponse { rows: Array<Record<string, unknown>>; columns: string[]; total_rows: number; downsampled: boolean }

// ---------------- Catalog Aggregation (proposed) ----------------
// The backend can optionally expose a single JSON (e.g. GET /catalog/manifest)
// that pre-joins feature catalog, primitive catalog, strategy tag stats and
// artifact counts to minimise round trips for the catalog UI. Schema below.

export interface CatalogArtifactCounts {
  models: number;
  reports: number;
  signals: number;
  logs: number;
  datasets: number;
  strategies: number;
}

export interface CatalogStrategyTagStat { tag: string; count: number }

export interface CatalogDatasetEntry { file: string; size: number; created: string }

export interface CatalogManifest {
  generated_at: string;
  git_commit?: string | null;
  data_version?: string | null;
  feature_count: number;
  primitive_count: number;
  features: FeatureDefinition[]; // optional full list
  primitives: PrimitiveDefinition[]; // optional full list
  strategy_tags: CatalogStrategyTagStat[]; // aggregated tag frequencies
  artifacts: CatalogArtifactCounts; // counts per artifact kind
  datasets?: CatalogDatasetEntry[]; // optional lightweight dataset listing
  version: number; // bump when schema changes
}

/*
Proposed backend endpoint: GET /catalog/manifest
Example JSON:
{
  "generated_at": "2025-09-16T10:12:03Z",
  "git_commit": "abc1234",
  "data_version": "20250915_fund_v2",
  "feature_count": 128,
  "primitive_count": 42,
  "features": [{"name":"close","description":"Daily close","group":"price"}, ...],
  "primitives": [{"name":"zscore","description":"Standard score","arity":1,"category":"transform"}, ...],
  "strategy_tags": [{"tag":"momentum","count":57},{"tag":"mean-reversion","count":31}],
  "artifacts": {"models":12,"reports":4,"signals":27,"logs":15,"datasets":6,"strategies":90},
  "datasets": [{"file":"datasets/panel/bars_eod_20250915.parquet","size":1048576,"created":"2025-09-15T22:00:01Z"}],
  "version": 1
}

Construction guidance (backend):
1. Load feature & primitive catalogs (existing endpoints or direct sources).
2. Scan strategy metadata store (or manifest) to compute tag frequencies.
3. Load artifacts/manifest.json and aggregate counts by kind.
4. Optionally list dataset artifacts (kind == 'dataset') with size & created timestamp.
5. Provide counts (feature_count, primitive_count) even if omitting full lists for size.
6. Set version=1 now; bump when schema changes to allow client conditional logic.
*/

