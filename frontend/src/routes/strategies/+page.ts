import type { PageLoad } from './$types';
import { getStrategies } from '$lib/api/client';
import type { StrategySummary } from '$lib/api/types';

const FALLBACK_STRATEGIES: StrategySummary[] = [
  {
    expr_hash: 'abc123',
    expr: 'clip(feat("c_sek")/lag(feat("c_sek"),1)-1)',
    metrics: { ann_return: 0.18, ann_vol: 0.12, ann_sharpe: 1.5, max_dd: -0.08 },
    complexity_score: 14.2,
    created_at: new Date().toISOString(),
    tags: ['momentum', 'fx'],
    notes: 'Placeholder strategy sourced from the architecture brief.'
  },
  {
    expr_hash: 'def456',
    expr: 'rank(zscore(feat("spread_eur_sek"))) > 0.5',
    metrics: { ann_return: 0.11, ann_vol: 0.09, ann_sharpe: 1.2, max_dd: -0.06 },
    complexity_score: 9.8,
    created_at: new Date().toISOString(),
    tags: ['mean-reversion'],
    notes: 'Fallback data shown while the API connection is offline.'
  }
];

export const load = (async ({ fetch, url }) => {
  const limit = Number(url.searchParams.get('limit') ?? 20);
  const offset = Number(url.searchParams.get('offset') ?? 0);

  try {
    const response = await getStrategies(fetch, { limit, offset });
    return {
      strategies: response.items,
      total: response.total,
      limit: response.limit,
      offset: response.offset,
      error: null,
      usingFallback: false
    };
  } catch (error) {
    return {
      strategies: FALLBACK_STRATEGIES,
      total: FALLBACK_STRATEGIES.length,
      limit,
      offset,
      error: 'Unable to reach the FastAPI service. Rendering fallback data instead.',
      usingFallback: true
    };
  }
}) satisfies PageLoad;
