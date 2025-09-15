import type {
  AggregateMetrics,
  BacktestRequest,
  BacktestResponse,
  BrokerPosition,
  FeatureCatalogResponse,
  HealthResponse,
  JobListResponse,
  JobLogResponse,
  JobStatus,
  OrderRequest,
  OrderResponse,
  PrimitiveCatalogResponse,
  StrategyListResponse,
  StrategySummary,
  TrainJobRequest
} from './types';

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

export async function launchBacktest(
  fetcher: typeof fetch,
  payload: BacktestRequest
): Promise<BacktestResponse> {
  return request(fetcher, '/backtest', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function launchTrainingJob(
  fetcher: typeof fetch,
  payload: TrainJobRequest
): Promise<JobStatus> {
  return request(fetcher, '/jobs/train', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
}

export async function getJobs(fetcher: typeof fetch): Promise<JobListResponse> {
  return request(fetcher, '/jobs');
}

export async function getJob(fetcher: typeof fetch, jobId: string): Promise<JobStatus> {
  return request(fetcher, `/jobs/${jobId}`);
}

export async function getJobLog(fetcher: typeof fetch, jobId: string): Promise<JobLogResponse> {
  return request(fetcher, `/jobs/${jobId}/log`);
}

export async function getFeatureCatalog(fetcher: typeof fetch): Promise<FeatureCatalogResponse> {
  return request(fetcher, '/config/features');
}

export async function getPrimitiveCatalog(fetcher: typeof fetch): Promise<PrimitiveCatalogResponse> {
  return request(fetcher, '/config/primitives');
}

export async function listBrokerPositions(fetcher: typeof fetch): Promise<BrokerPosition[]> {
  return request(fetcher, '/broker/positions');
}

export async function placeOrder(fetcher: typeof fetch, order: OrderRequest): Promise<OrderResponse> {
  return request(fetcher, '/broker/orders', {
    method: 'POST',
    body: JSON.stringify(order)
  });
}
