import type { PageLoad } from './$types';
import { getStrategy, getEquityCurve, getDailyReturns, getStrategyAnalysis, getStrategyAnalytics } from '$lib/api/client';
import type { StrategySummary, EquityCurve, DailyReturns, StrategyAnalysis, StrategyAnalytics } from '$lib/api/types';

interface StrategyDetailData {
    strategy: StrategySummary | null;
    equity: EquityCurve | null;
    returns: DailyReturns | null;
    analysis: StrategyAnalysis | null;
    analytics: StrategyAnalytics | null;
    // aggregated top-level fatal error (if strategy core missing)
    error: string | null;
    diagnostics: any | null;
    // granular fetch errors to surface partial load states
    fetchErrors: Record<string, { status?: number; message: string; detail?: any }>;
}

// Removed fallback placeholders: we now surface real API errors to the UI.

export const load = (async ({ fetch, params }) => {
    const { hash } = params;
    const fetchErrors: Record<string, { status?: number; message: string; detail?: any }> = {};

    async function safe<T>(key: string, fn: () => Promise<T>): Promise<T | null> {
        try {
            return await fn();
        } catch (e: any) {
            let status: number | undefined = undefined;
            let detail: any = null;
            try {
                const res = await fetch(`/api/strategies/${hash}/${key}`);
                if (!res.ok) {
                    status = res.status;
                    detail = await res.json().catch(() => null);
                }
            } catch { /* swallow */ }
            fetchErrors[key] = { status, message: e?.message || 'request failed', detail };
            return null;
        }
    }

    // Strategy core detail (if this fails we treat as fatal)
    let strategy: StrategySummary | null = null;
    try {
        strategy = await getStrategy(fetch, hash);
    } catch (e: any) {
        let diagnostics: any = null;
        let status: number | undefined;
        try {
            const res = await fetch(`/api/strategies/${hash}`);
            status = res.status;
            if (!res.ok) diagnostics = await res.json().catch(() => null);
        } catch { /* ignore */ }
        return {
            strategy: null,
            equity: null,
            returns: null,
            analysis: null,
            analytics: null,
            error: `Failed to load strategy core (${e?.message || 'error'})`,
            diagnostics,
            fetchErrors,
        } satisfies StrategyDetailData;
    }

    const [equity, returns, analytics, analysis] = await Promise.all([
        safe('curve', () => getEquityCurve(fetch, hash)),
        safe('returns', () => getDailyReturns(fetch, hash)),
        safe('analytics', () => getStrategyAnalytics(fetch, hash)),
        safe('analysis', () => getStrategyAnalysis(fetch, hash)),
    ]);

    return {
        strategy,
        equity,
        returns,
        analysis,
        analytics,
        error: null,
        diagnostics: null,
        fetchErrors,
    } satisfies StrategyDetailData;
}) satisfies PageLoad;