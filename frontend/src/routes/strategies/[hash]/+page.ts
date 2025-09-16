import type { PageLoad } from './$types';
import { getStrategy, getEquityCurve, getDailyReturns, getStrategyAnalysis } from '$lib/api/client';
import type { StrategySummary, EquityCurve, DailyReturns, StrategyAnalysis } from '$lib/api/types';

interface StrategyDetailData {
    strategy: StrategySummary | null;
    equity: EquityCurve | null;
    returns: DailyReturns | null;
    analysis: StrategyAnalysis | null;
    error: string | null;
    diagnostics: any | null;
}

// Removed fallback placeholders: we now surface real API errors to the UI.

export const load = (async ({ fetch, params }) => {
    const { hash } = params;
    try {
        const [strategy, equity, returns] = await Promise.all([
            getStrategy(fetch, hash),
            getEquityCurve(fetch, hash),
            getDailyReturns(fetch, hash)
        ]);
        const analysis = await getStrategyAnalysis(fetch, hash).catch(() => null);
        return { strategy, equity, returns, analysis, error: null, diagnostics: null } satisfies StrategyDetailData;
    } catch (err: any) {
        let message = 'Failed to load strategy.';
        let diagnostics: any = null;
        // Attempt re-fetch of detail for diagnostics body if available
        try {
            const res = await fetch(`/api/strategies/${hash}`);
            if (res.status !== 200) {
                diagnostics = await res.json().catch(() => null);
                message = `API ${res.status}: ${diagnostics?.detail?.error || diagnostics?.detail || message}`;
            }
        } catch { /* ignore */ }
        return { strategy: null, equity: null, returns: null, analysis: null, error: message, diagnostics } satisfies StrategyDetailData;
    }
}) satisfies PageLoad;