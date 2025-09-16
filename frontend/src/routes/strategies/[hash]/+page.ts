import type { PageLoad } from './$types';
import { getStrategy, getEquityCurve, getDailyReturns } from '$lib/api/client';
import type { StrategySummary, EquityCurve, DailyReturns } from '$lib/api/types';

interface StrategyDetailData {
    strategy: StrategySummary | null;
    equity: EquityCurve | null;
    returns: DailyReturns | null;
    error: string | null;
    usingFallback: boolean;
}

const NOW_ISO = new Date().toISOString();

const FALLBACK_STRATEGY: StrategySummary = {
    expr_hash: 'fallback',
    expr: 'zscore(feat("close")) > 0.0',
    metrics: { ann_return: 0.10, ann_vol: 0.12, ann_sharpe: 0.85, max_dd: -0.15 },
    complexity_score: 7.4,
    created_at: NOW_ISO,
    tags: ['fallback'],
    notes: 'Offline fallback strategy placeholder.'
};

const FALLBACK_EQUITY: EquityCurve = {
    expr_hash: 'fallback',
    base_currency: 'USD',
    dates: Array.from({ length: 30 }, (_, i) => new Date(Date.now() - (29 - i) * 86400000).toISOString().slice(0, 10)),
    equity: Array.from({ length: 30 }, (_, i) => 1_000_000 * (1 + i * 0.001 + Math.sin(i / 3) * 0.01))
};

const FALLBACK_RETURNS: DailyReturns = {
    expr_hash: 'fallback',
    dates: FALLBACK_EQUITY.dates,
    returns: FALLBACK_EQUITY.dates.map(() => (Math.random() - 0.5) * 0.01)
};

export const load = (async ({ fetch, params }) => {
    const { hash } = params;
    try {
        const [strategy, equity, returns] = await Promise.all([
            getStrategy(fetch, hash),
            getEquityCurve(fetch, hash),
            getDailyReturns(fetch, hash)
        ]);
        return {
            strategy,
            equity,
            returns,
            error: null,
            usingFallback: false
        } satisfies StrategyDetailData;
    } catch (err) {
        return {
            strategy: FALLBACK_STRATEGY,
            equity: FALLBACK_EQUITY,
            returns: FALLBACK_RETURNS,
            error: 'Unable to reach API – showing fallback strategy.',
            usingFallback: true
        } satisfies StrategyDetailData;
    }
}) satisfies PageLoad;