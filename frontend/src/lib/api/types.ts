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
}

export interface EquityCurve {
  expr_hash: string;
  base_currency: string;
  dates: string[];
  equity: number[];
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

export interface BacktestRequest {
  expr: string;
  seed?: number;
  persist?: boolean;
}

export interface BacktestResponse {
  job_id: string | null;
  status: 'queued' | 'completed' | 'failed';
  result?: StrategySummary | null;
}

export interface JobParams {
  cap?: number | null;
  max_lev?: number | null;
  execution_lag?: number | null;
  smooth_ema?: number | null;
  limit_score?: number | null;
}

export interface TrainJobRequest {
  n: number;
  seed?: number;
  workers?: number;
  params: JobParams;
}

export interface JobStatus {
  job_id: string;
  type: 'train' | 'backtest';
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress?: number | null;
  processed?: number | null;
  submitted_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  summary?: StrategySummary | null;
}

export interface JobListResponse {
  items: JobStatus[];
  total: number;
}

export interface JobLogEntry {
  ts: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
  message: string;
  context?: Record<string, unknown>;
}

export interface JobLogResponse {
  job_id: string;
  entries: JobLogEntry[];
}

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

export interface BrokerPosition {
  symbol: string;
  quantity: number;
  avg_price: number;
  market_value: number;
  currency: string;
}

export interface OrderRequest {
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  order_type?: 'mkt' | 'lmt';
  limit_price?: number | null;
}

export interface OrderResponse {
  order_id: string;
  status: 'accepted' | 'rejected';
  submitted_at: string;
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  order_type: 'mkt' | 'lmt';
}

export interface HealthResponse {
  status: 'ok' | 'degraded';
  version: string;
  git_commit?: string | null;
}
