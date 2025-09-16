import type { PageLoad } from './$types';
import { getFeatureCatalog, getPrimitiveCatalog, getCatalogManifest, getArtifactManifest, getStrategies } from '$lib/api/client';
import type { FeatureCatalogResponse, PrimitiveCatalogResponse, CatalogManifest, StrategyListResponse, ArtifactManifest } from '$lib/api/types';

interface CatalogData {
    features: FeatureCatalogResponse['features'];
    primitives: PrimitiveCatalogResponse['primitives'];
    artifactCounts: Record<string, number>;
    strategyTagStats: { tag: string; count: number }[];
    datasets: { file: string; size: number; created: string }[];
    error: string | null;
    usingFallback: boolean;
    aggregated: boolean; // whether catalog manifest endpoint succeeded
}

const FALLBACK_FEATURES: FeatureCatalogResponse['features'] = [
    { name: 'close', description: 'Daily close price', group: 'price' },
    { name: 'volume', description: 'Daily volume', group: 'volume' }
];

const FALLBACK_PRIMITIVES: PrimitiveCatalogResponse['primitives'] = [
    { name: 'zscore', description: 'Standard score normalisation', arity: 1, category: 'transform' },
    { name: 'rank', description: 'Cross-sectional ranking 0-1', arity: 1, category: 'transform' }
];

function computeTagStats(strategies: StrategyListResponse | null): { tag: string; count: number }[] {
    if (!strategies) return [];
    const counts: Record<string, number> = {};
    for (const s of strategies.items) {
        if (s.tags) for (const t of s.tags) counts[t] = (counts[t] || 0) + 1;
    }
    return Object.entries(counts).map(([tag, count]) => ({ tag, count })).sort((a, b) => b.count - a.count);
}

function deriveArtifactCounts(manifest: ArtifactManifest | null): Record<string, number> {
    if (!manifest) return {};
    const counts: Record<string, number> = {};
    for (const e of manifest.entries) counts[e.kind] = (counts[e.kind] || 0) + 1;
    return counts;
}

function extractDatasets(manifest: ArtifactManifest | null): { file: string; size: number; created: string }[] {
    if (!manifest) return [];
    return manifest.entries.filter(e => e.kind === 'dataset').map(e => ({ file: e.file, size: e.size, created: e.created }));
}

export const load = (async ({ fetch }) => {
    // 1. Try aggregated catalog manifest (future endpoint)
    let aggregated: CatalogManifest | null = null;
    try {
        aggregated = await getCatalogManifest(fetch);
    } catch { }

    if (aggregated) {
        const artifactCounts: Record<string, number> = { ...aggregated.artifacts } as unknown as Record<string, number>;
        return {
            features: aggregated.features,
            primitives: aggregated.primitives,
            artifactCounts,
            strategyTagStats: aggregated.strategy_tags,
            datasets: aggregated.datasets ?? [],
            error: null,
            usingFallback: false,
            aggregated: true
        } satisfies CatalogData;
    }

    // 2. Fallback: call individual endpoints and derive aggregates locally
    try {
        const [features, primitives, strategies, artifactManifest] = await Promise.all([
            getFeatureCatalog(fetch),
            getPrimitiveCatalog(fetch),
            getStrategies(fetch, { limit: 500, offset: 0 }), // large cap for tag stats
            getArtifactManifest(fetch)
        ]).catch(async (err) => { throw err; });

        const tagStats = computeTagStats(strategies);
        const artifactCounts = deriveArtifactCounts(artifactManifest);
        const datasets = extractDatasets(artifactManifest);

        return {
            features: features.features,
            primitives: primitives.primitives,
            artifactCounts,
            strategyTagStats: tagStats,
            datasets,
            error: null,
            usingFallback: false,
            aggregated: false
        } satisfies CatalogData;
    } catch (err) {
        return {
            features: FALLBACK_FEATURES,
            primitives: FALLBACK_PRIMITIVES,
            artifactCounts: {},
            strategyTagStats: [],
            datasets: [],
            error: 'Unable to reach API – showing fallback catalog.',
            usingFallback: true,
            aggregated: false
        } satisfies CatalogData;
    }
}) satisfies PageLoad;