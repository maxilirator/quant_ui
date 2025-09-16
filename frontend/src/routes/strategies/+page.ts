import type { PageLoad } from './$types';
import { getStrategies } from '$lib/api/client';
import type { StrategySummary } from '$lib/api/types';

export const load = (async ({ fetch, url }) => {
  const qp = url.searchParams;
  const limit = Math.max(1, Math.min(200, Number(qp.get('limit') ?? 21)));
  const page = Math.max(1, Number(qp.get('page') ?? 1));
  const order = qp.get('order') || undefined;
  // Raw filter strings (empty string means not provided). Kept for form repopulation.
  const filters = {
    min_return: qp.get('min_return') || '',
    max_vol: qp.get('max_vol') || '',
    min_sharpe: qp.get('min_sharpe') || '',
    max_dd: qp.get('max_dd') || '',
    created_after: qp.get('created_after') || ''
  };

  // Normalize numeric inputs. Heuristics:
  // - Allow percent sign (e.g. 5%, 12.5%) -> divide by 100.
  // - For annual return / vol values > 1.5 assume percent (5 => 0.05).
  // - max_dd is usually negative or fractional (e.g. -0.2). If user enters -5 assume -0.05.
  function parseMaybePercent(raw: string, field: 'return' | 'vol' | 'sharpe' | 'dd'): number | null {
    if (!raw || raw.trim() === '') return null;
    const trimmed = raw.trim();
    const pct = trimmed.endsWith('%');
    const num = parseFloat(trimmed.replace(/%$/, ''));
    if (Number.isNaN(num)) return null;
    if (field === 'sharpe') return num; // Sharpe ratio left as-is
    if (field === 'dd') {
      // Drawdown more negative is worse. Accept negative numbers or small fractions.
      if (pct) return num / 100 * (num >= 0 ? -1 : 1); // '5%' -> -0.05 (assuming intention of 5% drawdown)
      if (num <= -1) return num / 100; // -5 -> -0.05
      if (num > 0 && num > 1) return -num / 100; // 5 -> -0.05 (user likely omitted minus)
      return num; // already fractional (e.g. -0.12)
    }
    // Return / Vol
    let value = num;
    if (pct) value = num / 100;
    else if (value > 1.5) value = value / 100; // treat 5 as 5%
    return value;
  }

  interface ActiveFilters { [k: string]: number | Date }
  const active: ActiveFilters = {};
  const normalized: Record<string, any> = {};
  const rMinRet = parseMaybePercent(filters.min_return, 'return'); if (rMinRet !== null) { active.min_return = rMinRet; normalized.min_return = rMinRet; }
  const rMaxVol = parseMaybePercent(filters.max_vol, 'vol'); if (rMaxVol !== null) { active.max_vol = rMaxVol; normalized.max_vol = rMaxVol; }
  const rMinSharpe = parseMaybePercent(filters.min_sharpe, 'sharpe'); if (rMinSharpe !== null) { active.min_sharpe = rMinSharpe; normalized.min_sharpe = rMinSharpe; }
  const rMaxDD = parseMaybePercent(filters.max_dd, 'dd'); if (rMaxDD !== null) { active.max_dd = rMaxDD; normalized.max_dd = rMaxDD; }
  if (filters.created_after.trim()) {
    const d = new Date(filters.created_after);
    if (!Number.isNaN(d.getTime())) { active.created_after = d; normalized.created_after = d.toISOString(); }
  }

  try {
    // Fetch a broader slice (first 1000) then filter/sort/paginate locally for now.
    const upstreamLimit = 1000;
    const response = await getStrategies(fetch, { limit: upstreamLimit, offset: 0, order: undefined });
    let all: StrategySummary[] = response.items.slice();

    // Apply server-requested order locally to entire set
    function applyOrder(items: StrategySummary[], spec?: string): StrategySummary[] {
      if (!spec) return items;
      const keys = spec.split(',').map(k => k.trim()).filter(Boolean);
      const out = items.slice();
      for (let i = keys.length - 1; i >= 0; i--) {
        const token = keys[i];
        const parts = token.split('_');
        const dir = parts.pop() || 'asc';
        const field = parts.join('_');
        const reverse = dir === 'desc';
        out.sort((a, b) => {
          const metricsMap: Record<string, number> = {
            ann_return: a.metrics.ann_return - b.metrics.ann_return,
            ann_vol: a.metrics.ann_vol - b.metrics.ann_vol,
            ann_sharpe: a.metrics.ann_sharpe - b.metrics.ann_sharpe,
            max_dd: a.metrics.max_dd - b.metrics.max_dd,
            complexity_score: a.complexity_score - b.complexity_score
          };
          if (field in metricsMap) {
            const diff = metricsMap[field];
            return reverse ? -diff : diff;
          }
          if (field === 'created_at') {
            const diff = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
            return reverse ? -diff : diff;
          }
          if (field === 'expr_hash') {
            const diff = a.expr_hash.localeCompare(b.expr_hash);
            return reverse ? -diff : diff;
          }
          return 0;
        });
      }
      return out;
    }

    // Filters
    function passes(s: StrategySummary) {
      if (typeof active.min_return === 'number' && s.metrics.ann_return <= active.min_return) return false;
      if (typeof active.max_vol === 'number' && s.metrics.ann_vol > active.max_vol) return false;
      if (typeof active.min_sharpe === 'number' && s.metrics.ann_sharpe < active.min_sharpe) return false;
      if (typeof active.max_dd === 'number' && s.metrics.max_dd < active.max_dd) return false; // Require drawdown >= threshold (less severe)
      if (active.created_after instanceof Date && new Date(s.created_at) < active.created_after) return false;
      return true;
    }

    const filtered = all.filter(passes);
    const ordered = applyOrder(filtered, order);
    const total = ordered.length;
    const totalPages = Math.max(1, Math.ceil(total / limit));
    const safePage = Math.min(page, totalPages);
    const start = (safePage - 1) * limit;
    const pageItems = ordered.slice(start, start + limit);

    function pageHref(p: number) {
      const params = new URLSearchParams();
      params.set('page', String(p));
      params.set('limit', String(limit));
      if (order) params.set('order', order);
      Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
      return `?${params.toString()}`;
    }

    return {
      strategies: pageItems,
      total,
      limit,
      page: safePage,
      totalPages,
      order: order || null,
      filters,
      prevHref: safePage > 1 ? pageHref(safePage - 1) : null,
      nextHref: safePage < totalPages ? pageHref(safePage + 1) : null,
      debug: {
        upstream_count: all.length,
        filtered_count: filtered.length,
        ordered_slice: pageItems.length,
        applied_order: order || null,
        filters_raw: filters,
        filters_active: active,
        filters_normalized: normalized,
        start_index: start,
      },
      error: null,
      usingFallback: false,
      diagnostics: null
    };
  } catch (err: any) {
    // Try to parse structured diagnostics if JSON body came back
    let message = 'Failed to load strategies.';
    let diagnostics: any = null;
    if (err?.message?.includes('status')) {
      // Attempt diagnostics fetch without relying on removed offset param (page=1)
      try {
        const res = await fetch(`/api/strategies?limit=${limit}&offset=0`);
        if (res.status !== 200) {
          diagnostics = await res.json().catch(() => null);
          message = `API ${res.status}: ${diagnostics?.detail?.error || diagnostics?.detail || 'Unable to load strategies'}`;
        }
      } catch { /* ignore nested error */ }
    }
    return {
      strategies: [] as StrategySummary[],
      total: 0,
      limit,
      page: 1,
      totalPages: 1,
      order: order || null,
      filters,
      prevHref: null,
      nextHref: null,
      debug: { error: true, message, filters_raw: filters },
      error: message,
      usingFallback: false,
      diagnostics
    };
  }
}) satisfies PageLoad;
