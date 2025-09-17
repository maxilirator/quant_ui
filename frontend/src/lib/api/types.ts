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

// Strategy analytics (drawdowns & rolling metrics)
export interface DrawdownEvent {
  start: string;
  trough: string;
  recovery?: string | null;
  depth: number; // negative fraction
  length: number; // days total
  days_to_trough: number;
}

export interface StrategyAnalytics {
  expr_hash: string;
  as_of: string;
  dd_dates: string[];
  drawdowns: number[];
  top_drawdowns: DrawdownEvent[];
  window?: number | null;
  rolling_return: number[];
  rolling_vol: number[];
  rolling_sharpe: number[];
  monthly_returns: { year: number; month: number; return: number }[];
  return_histogram?: { bins: { start: number; end: number; count: number }[]; min: number; max: number; bucket_size: number; total: number } | null;
  dist_stats?: { mean: number; std: number; skew: number; kurtosis: number; p5: number; p50: number; p95: number; count: number; negative_share: number; downside_dev: number; sortino: number } | null;
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

// Control API types
export interface ControlTaskParam { name: string; type: string; required: boolean; default?: any; description?: string | null }
export interface ControlTask { id: string; summary: string; category: string; params: ControlTaskParam[] }
export interface ControlJob { id: string; task_id: string; status: string; created_at: number; started_at?: number | null; finished_at?: number | null; exit_code?: number | null; error?: string | null; stdout_tail: string[]; stderr_tail: string[]; pid?: number | null }
export interface ControlJobLogs { stdout: string[]; stderr: string[]; truncated: boolean }
export interface ControlCSVFile { path: string; size: number; mtime: number }
export interface ControlFileEntry { path: string; name: string; size: number; mtime: number }
export interface ControlModeList { modes: string[]; default: string }
export interface ControlMetricInfo { key: string; label: string; description: string }

