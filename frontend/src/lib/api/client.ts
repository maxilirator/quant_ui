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
import type { CatalogManifest, StrategyAnalysis, StrategyAnalytics } from './types';

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

export async function getStrategyAnalysis(fetcher: typeof fetch, exprHash: string): Promise<StrategyAnalysis> {
  return request(fetcher, `/strategies/${exprHash}/analysis`);
}

export async function getStrategyAnalytics(fetcher: typeof fetch, exprHash: string, window: number = 252): Promise<StrategyAnalytics> {
  return request(fetcher, `/strategies/${exprHash}/analytics?window=${window}`);
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

// Control API additions
import type { ControlTask, ControlJob, ControlJobLogs, ControlCSVFile, ControlFileEntry, ControlModeList, ControlMetricInfo } from './types';

export async function listControlTasks(fetcher: typeof fetch): Promise<ControlTask[]> {
  return request(fetcher, '/control/tasks');
}

export async function runControlTask(fetcher: typeof fetch, taskId: string, params: Record<string, any>): Promise<ControlJob> {
  return request(fetcher, `/control/tasks/${taskId}/run`, {
    method: 'POST',
    body: JSON.stringify({ params })
  });
}

export async function listControlJobs(fetcher: typeof fetch): Promise<ControlJob[]> {
  return request(fetcher, '/control/jobs');
}

export async function getControlJob(fetcher: typeof fetch, jobId: string): Promise<ControlJob> {
  return request(fetcher, `/control/jobs/${jobId}`);
}

export async function getControlJobLogs(fetcher: typeof fetch, jobId: string): Promise<ControlJobLogs> {
  return request(fetcher, `/control/jobs/${jobId}/logs`);
}

export async function cancelControlJob(fetcher: typeof fetch, jobId: string): Promise<ControlJob> {
  return request(fetcher, `/control/jobs/${jobId}/cancel`, { method: 'POST' });
}

export async function listControlCSVs(fetcher: typeof fetch): Promise<ControlCSVFile[]> {
  return request(fetcher, '/control/datasets/csv');
}

export interface ControlMeta { dev_mode: boolean; version: string; git_commit?: string | null; data_version?: string | null; quant_core_root?: string | null; artifacts_root?: string | null }
export async function getControlMeta(fetcher: typeof fetch): Promise<ControlMeta> {
  return request(fetcher, '/control/meta');
}

// Listing endpoints
export async function listRunsDB(fetcher: typeof fetch): Promise<ControlFileEntry[]> { return request(fetcher, '/control/list/runsdb'); }
export async function listSignalFiles(fetcher: typeof fetch): Promise<ControlFileEntry[]> { return request(fetcher, '/control/list/signals'); }
export async function listReturnFiles(fetcher: typeof fetch): Promise<ControlFileEntry[]> { return request(fetcher, '/control/list/returns'); }
export async function listStrategyConfigs(fetcher: typeof fetch): Promise<ControlFileEntry[]> { return request(fetcher, '/control/list/strategies_cfg'); }
export async function listModes(fetcher: typeof fetch): Promise<ControlModeList> { return request(fetcher, '/control/introspect/modes'); }
export async function listMetrics(fetcher: typeof fetch): Promise<ControlMetricInfo[]> { return request(fetcher, '/control/introspect/metrics'); }
export async function fetchConfigFile(fetcher: typeof fetch, path: string): Promise<{ path: string; content: string }> { return request(fetcher, `/control/config/file?path=${encodeURIComponent(path)}`); }
export async function listGenericConfigs(fetcher: typeof fetch): Promise<ControlFileEntry[]> { return request(fetcher, '/control/list/configs'); }

// Data browser endpoints
export interface DomainMeta { domain: string; rows: number; cols: number; type: string; features: string[] }
export interface DomainsResponse { domains: DomainMeta[]; skipped: { domain?: string; reason?: string }[] }
export async function listDataDomains(fetcher: typeof fetch, refresh = false): Promise<DomainsResponse> {
  return request(fetcher, `/control/data/domains${refresh ? '?refresh=1' : ''}`);
}
export interface DomainSample { domain: string; columns: string[]; rows: Record<string, any>[] }
export async function getDomainSample(fetcher: typeof fetch, domain: string, limit = 50): Promise<DomainSample> {
  return request(fetcher, `/control/data/sample?domain=${encodeURIComponent(domain)}&limit=${limit}`);
}
export interface DataFileEntry { path: string; kind: string; size: number; mtime: number }
export async function listDataFiles(fetcher: typeof fetch): Promise<DataFileEntry[]> {
  return request(fetcher, '/control/data/files');
}
export interface FilePreview { path: string; kind: string; columns?: string[]; rows?: Record<string, any>[]; text?: string }
export async function previewDataFile(fetcher: typeof fetch, path: string, limit = 50, table?: string): Promise<FilePreview> {
  const qs = new URLSearchParams({ path, limit: String(limit) });
  if (table) qs.set('table', table);
  return request(fetcher, `/control/data/file/preview?${qs.toString()}`);
}

