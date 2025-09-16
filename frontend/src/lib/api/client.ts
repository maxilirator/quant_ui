import type {
  AggregateMetrics,
  FeatureCatalogResponse,
  HealthResponse,
  PrimitiveCatalogResponse,
  StrategyListResponse,
  StrategySummary,
  EquityCurve,
  DailyReturns
} from './types';
import type { CatalogManifest } from './types';

const API_BASE_PATH = '/api';

async function request<T>(fetcher: typeof fetch, path: string, init?: RequestInit): Promise<T> {
  const response = await fetcher(`${API_BASE_PATH}${path}`, {
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}

export async function getHealth(fetcher: typeof fetch): Promise<HealthResponse> {
  return request(fetcher, '/health');
}

export interface StrategyQueryParams {
  limit?: number;
  offset?: number;
  order?: string;
}

export async function getStrategies(
  fetcher: typeof fetch,
  params: StrategyQueryParams = {}
): Promise<StrategyListResponse> {
  const search = new URLSearchParams();
  if (params.limit !== undefined) search.set('limit', String(params.limit));
  if (params.offset !== undefined) search.set('offset', String(params.offset));
  if (params.order) search.set('order', params.order);

  const query = search.toString();
  const path = query ? `/strategies?${query}` : '/strategies';
  return request(fetcher, path);
}

export async function getStrategy(fetcher: typeof fetch, exprHash: string): Promise<StrategySummary> {
  return request(fetcher, `/strategies/${exprHash}`);
}

export async function getAggregateMetrics(fetcher: typeof fetch): Promise<AggregateMetrics> {
  return request(fetcher, '/metrics/aggregate');
}

export async function getFeatureCatalog(fetcher: typeof fetch): Promise<FeatureCatalogResponse> {
  return request(fetcher, '/config/features');
}

export async function getPrimitiveCatalog(fetcher: typeof fetch): Promise<PrimitiveCatalogResponse> {
  return request(fetcher, '/config/primitives');
}

// ---- New read-only additions ----

export async function getEquityCurve(fetcher: typeof fetch, exprHash: string): Promise<EquityCurve> {
  return request(fetcher, `/strategies/${exprHash}/curve`);
}

export async function getDailyReturns(fetcher: typeof fetch, exprHash: string): Promise<DailyReturns> {
  return request(fetcher, `/strategies/${exprHash}/returns`);
}

export interface PanelSliceParams {
  start?: string;
  end?: string;
  tickers?: string[];
  limit_tickers?: number;
}

export interface PanelSliceResponse {
  rows: Array<Record<string, unknown>>;
  columns: string[];
  total_rows: number;
  downsampled: boolean;
}

export async function getPanelSlice(fetcher: typeof fetch, params: PanelSliceParams = {}): Promise<PanelSliceResponse> {
  const search = new URLSearchParams();
  if (params.start) search.set('start', params.start);
  if (params.end) search.set('end', params.end);
  if (params.tickers && params.tickers.length) search.set('tickers', params.tickers.join(','));
  if (params.limit_tickers !== undefined) search.set('limit_tickers', String(params.limit_tickers));
  const qs = search.toString();
  return request(fetcher, `/panel/slice${qs ? `?${qs}` : ''}`);
}

// Artifacts manifest & filtered lists
export interface ArtifactEntry { file: string; sha256: string; size: number; created: string; kind: string; }
export interface ArtifactManifest { generated_at: string; git_commit?: string | null; data_version?: string | null; entries: ArtifactEntry[]; version: number; }

export async function getArtifactManifest(fetcher: typeof fetch): Promise<ArtifactManifest> {
  return request(fetcher, '/artifacts/manifest');
}

export async function listModelArtifacts(fetcher: typeof fetch): Promise<ArtifactEntry[]> {
  const r = await request<{ models: ArtifactEntry[] }>(fetcher, '/artifacts/models');
  return r.models;
}

export async function listReportArtifacts(fetcher: typeof fetch): Promise<ArtifactEntry[]> {
  const r = await request<{ reports: ArtifactEntry[] }>(fetcher, '/artifacts/reports');
  return r.reports;
}

export async function listSignalArtifacts(fetcher: typeof fetch): Promise<ArtifactEntry[]> {
  const r = await request<{ signals: ArtifactEntry[] }>(fetcher, '/artifacts/signals');
  return r.signals;
}

export async function listLogArtifacts(fetcher: typeof fetch): Promise<ArtifactEntry[]> {
  const r = await request<{ logs: ArtifactEntry[] }>(fetcher, '/artifacts/logs');
  return r.logs;
}

export async function listDatasetArtifacts(fetcher: typeof fetch): Promise<ArtifactEntry[]> {
  const r = await request<{ datasets: ArtifactEntry[] }>(fetcher, '/artifacts/datasets');
  return r.datasets;
}

export async function listStrategyArtifacts(fetcher: typeof fetch): Promise<ArtifactEntry[]> {
  const r = await request<{ strategies: ArtifactEntry[] }>(fetcher, '/artifacts/strategies');
  return r.strategies;
}

// Catalog aggregation (optional backend endpoint e.g. /catalog/manifest)
export async function getCatalogManifest(fetcher: typeof fetch): Promise<CatalogManifest> {
  return request(fetcher, '/catalog/manifest');
}

