<script lang="ts">
  import type { PageData } from "./$types";
  import LineChart from "$lib/components/LineChart.svelte";
  import ReturnsBarChart from "$lib/components/ReturnsBarChart.svelte";
  import Histogram from "$lib/components/Histogram.svelte";
  import MonthlyHeatmap from "$lib/components/MonthlyHeatmap.svelte";
  // simple CSV export helpers (client-side only)
  function toCSV(rows: Array<Record<string, any>>): string {
    if (!rows.length) return "";
    const set = rows.reduce<Set<string>>((s, r: Record<string, any>) => {
      Object.keys(r).forEach((k) => s.add(k));
      return s;
    }, new Set<string>());
    const cols = Array.from(set);
    const escape = (v: any) => {
      if (v == null) return "";
      const s = String(v);
      return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    return [
      cols.join(","),
      ...rows.map((r) => cols.map((c) => escape(r[c])).join(",")),
    ].join("\n");
  }
  function download(name: string, csv: string) {
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }
  function exportDaily() {
    if (!data.returns) return;
    const rows = data.returns.dates.map((d, i) => ({
      date: d,
      return: data.returns!.returns[i],
    }));
    download(
      `${data.strategy?.expr_hash || "strategy"}_daily_returns.csv`,
      toCSV(rows)
    );
  }
  function exportMonthly() {
    if (!data.analytics?.monthly_returns?.length) return;
    download(
      `${data.strategy?.expr_hash || "strategy"}_monthly_returns.csv`,
      toCSV(data.analytics.monthly_returns)
    );
  }
  function exportHistogram() {
    if (!data.analytics?.return_histogram?.bins?.length) return;
    download(
      `${data.strategy?.expr_hash || "strategy"}_histogram.csv`,
      toCSV(data.analytics.return_histogram.bins)
    );
  }
  let { data }: { data: PageData } = $props();

  const formatPercent = (v: number) => `${(v * 100).toFixed(2)}%`;

  // Simple client-side sparkline path generator for equity curve
  let path = "";
  if (data.equity?.equity?.length) {
    const values = data.equity.equity;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const w = 320;
    const h = 80;
    path = values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * w;
        const y = h - ((v - min) / span) * h;
        return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
  }
  const height = 120;
</script>

<svelte:head>
  <title>Strategy {data.strategy?.expr_hash} • Quant UI</title>
</svelte:head>

<nav class="crumbs"><a href="/strategies">← Strategies</a></nav>

{#if data.error}
  <div class="banner">
    <strong>{data.error}</strong>
    {#if data.diagnostics?.detail}
      <pre class="diag">{JSON.stringify(data.diagnostics.detail, null, 2)}</pre>
    {:else if data.diagnostics}
      <pre class="diag">{JSON.stringify(data.diagnostics, null, 2)}</pre>
    {/if}
  </div>
{/if}
{#if Object.keys(data.fetchErrors || {}).length}
  <div class="banner warn">
    <strong>Partial data issues:</strong>
    <ul class="errs">
      {#each Object.entries(data.fetchErrors) as [k, v]}
        <li>
          <code>{k}</code>: {v.status || ""}
          {v.message}
          {#if v.detail?.detail?.error}- {v.detail.detail.error}{/if}
        </li>
      {/each}
    </ul>
  </div>
{/if}

<section class="header">
  <div>
    <h2>{data.strategy?.expr_hash}</h2>
    <pre class="expr">{data.strategy?.expr}</pre>
    {#if data.strategy?.tags?.length}
      <ul class="tags">
        {#each data.strategy.tags as t}<li>{t}</li>{/each}
      </ul>
    {/if}
    {#if data.analysis}
      <div class="analysis">
        <div>
          <h4>Features Used</h4>
          {#if data.analysis.features_used.length === 0}
            <p class="empty">No feature references detected.</p>
          {:else}
            <ul class="pill-list">
              {#each data.analysis.features_used as f}<li>{f}</li>{/each}
            </ul>
          {/if}
        </div>
        <div>
          <h4>Primitives Used</h4>
          {#if data.analysis.primitives_used.length === 0}
            <p class="empty">No primitive references detected.</p>
          {:else}
            <ul class="pill-list alt">
              {#each data.analysis.primitives_used as p}<li>{p}</li>{/each}
            </ul>
          {/if}
        </div>
        <div class="metrics-inline">
          <span title="Expression length in characters"
            >len: {data.analysis.expr_length}</span
          >
          <span title="Approximate token count"
            >tokens: {data.analysis.token_count}</span
          >
        </div>
      </div>
    {/if}
  </div>
  <div class="metrics">
    <div>
      <span>Ann Return</span><strong
        >{formatPercent(data.strategy?.metrics.ann_return || 0)}</strong
      >
    </div>
    <div>
      <span>Vol</span><strong
        >{formatPercent(data.strategy?.metrics.ann_vol || 0)}</strong
      >
    </div>
    <div>
      <span>Sharpe</span><strong
        >{(data.strategy?.metrics.ann_sharpe || 0).toFixed(2)}</strong
      >
    </div>
    <div>
      <span>Max DD</span><strong
        >{formatPercent(data.strategy?.metrics.max_dd || 0)}</strong
      >
    </div>
  </div>
</section>

<section class="chart-block">
  <h3>Equity Curve</h3>
  {#if data.equity?.equity?.length}
    <LineChart
      {height}
      series={[
        {
          name: data.strategy?.expr_hash || "strategy",
          points: data.equity!.dates.map((d, i) => ({
            x: d,
            y: data.equity!.equity[i],
          })),
        },
      ]}
      showDots={true}
      yFormat={(v) => v.toFixed(3)}
    />
  {:else}
    <p>No equity data.</p>
  {/if}
</section>

<section class="benchmark-block">
  <h3>Benchmark (placeholder)</h3>
  <p class="empty">No benchmark series configured yet.</p>
</section>

<section class="returns-block">
  <h3>Daily Returns (last {data.returns?.returns.length} days)</h3>
  {#if data.returns}
    <ReturnsBarChart
      dates={data.returns.dates}
      values={data.returns.returns}
      height={140}
    />
    <div class="export-row">
      <button onclick={exportDaily}>Export Daily CSV</button>
    </div>
  {:else}
    <p>No return data.</p>
  {/if}
</section>

<section class="drawdown-block">
  <h3>Drawdown</h3>
  {#if data.analytics && data.analytics.drawdowns && data.analytics.drawdowns.length}
    <LineChart
      height={140}
      series={[
        {
          name: "Drawdown",
          points: data.analytics.dd_dates.map((d, i) => ({
            x: d,
            y: data.analytics!.drawdowns[i],
          })),
        },
      ]}
      showDots={false}
      yFormat={(v) => (v * 100).toFixed(2) + "%"}
    />
    {#if data.analytics.top_drawdowns?.length}
      <table class="dd-table">
        <thead>
          <tr
            ><th>#</th><th>Start</th><th>Trough</th><th>Recovery</th><th
              >Depth</th
            ><th>Days ↓</th><th>Length</th></tr
          >
        </thead>
        <tbody>
          {#each data.analytics.top_drawdowns as ev, i}
            <tr>
              <td>{i + 1}</td>
              <td>{ev.start}</td>
              <td>{ev.trough}</td>
              <td>{ev.recovery || "—"}</td>
              <td class="neg">{(ev.depth * 100).toFixed(2)}%</td>
              <td>{ev.days_to_trough}</td>
              <td>{ev.length}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {:else}
    <p>No drawdown analytics.</p>
  {/if}
</section>

<section class="rolling-block">
  <h3>Rolling Metrics (window {data.analytics?.window || 252}d)</h3>
  {#if data.analytics && data.analytics.rolling_return && data.analytics.rolling_return.length}
    <div class="rolling-grid">
      <div>
        <h4>Rolling Return</h4>
        <LineChart
          height={120}
          series={[
            {
              name: "Return",
              points: data.analytics.dd_dates
                .map((d, i) => ({ x: d, y: data.analytics!.rolling_return[i] }))
                .filter((p) => p.y === p.y),
            },
          ]}
          showDots={false}
          yFormat={(v) => (v * 100).toFixed(1) + "%"}
        />
      </div>
      <div>
        <h4>Rolling Vol</h4>
        <LineChart
          height={120}
          series={[
            {
              name: "Vol",
              points: data.analytics.dd_dates
                .map((d, i) => ({ x: d, y: data.analytics!.rolling_vol[i] }))
                .filter((p) => p.y === p.y),
            },
          ]}
          showDots={false}
          yFormat={(v) => (v * 100).toFixed(1) + "%"}
        />
      </div>
      <div>
        <h4>Rolling Sharpe</h4>
        <LineChart
          height={120}
          series={[
            {
              name: "Sharpe",
              points: data.analytics.dd_dates
                .map((d, i) => ({ x: d, y: data.analytics!.rolling_sharpe[i] }))
                .filter((p) => p.y === p.y),
            },
          ]}
          showDots={false}
          yFormat={(v) => v.toFixed(2)}
        />
      </div>
    </div>
  {:else}
    <p>No rolling metrics.</p>
  {/if}
</section>

<section class="distribution-block">
  <h3>Return Distribution</h3>
  {#if data.analytics?.return_histogram?.bins?.length}
    <Histogram
      bins={data.analytics.return_histogram.bins}
      total={data.analytics.return_histogram.total}
      valueFormat={(v) => (v * 100).toFixed(2) + "%"}
      height={120}
    />
    <div class="export-row">
      <button onclick={exportHistogram}>Export Histogram CSV</button>
    </div>
  {:else}
    <p class="empty">No histogram data.</p>
  {/if}
</section>

<section class="monthly-block">
  <h3>Monthly Performance</h3>
  {#if data.analytics?.monthly_returns?.length}
    <MonthlyHeatmap data={data.analytics.monthly_returns} />
    <div class="export-row">
      <button onclick={exportMonthly}>Export Monthly CSV</button>
    </div>
  {:else}
    <p class="empty">No monthly data.</p>
  {/if}
</section>

{#if data.analytics?.dist_stats}
  <section class="stats-block">
    <h3>Distribution Stats</h3>
    <table class="stats-table">
      <tbody>
        <tr
          ><th>Count</th><td>{data.analytics.dist_stats.count}</td><th
            >Neg Days %</th
          ><td
            >{(data.analytics.dist_stats.negative_share * 100).toFixed(1)}%</td
          ></tr
        >
        <tr
          ><th>Mean</th><td
            >{(data.analytics.dist_stats.mean * 100).toFixed(3)}%</td
          ><th>Std</th><td
            >{(data.analytics.dist_stats.std * 100).toFixed(3)}%</td
          ></tr
        >
        <tr
          ><th>Skew</th><td>{data.analytics.dist_stats.skew?.toFixed(2)}</td><th
            >Kurtosis</th
          ><td>{data.analytics.dist_stats.kurtosis?.toFixed(2)}</td></tr
        >
        <tr
          ><th>P5</th><td>{(data.analytics.dist_stats.p5 * 100).toFixed(2)}%</td
          ><th>P50</th><td
            >{(data.analytics.dist_stats.p50 * 100).toFixed(2)}%</td
          ></tr
        >
        <tr
          ><th>P95</th><td
            >{(data.analytics.dist_stats.p95 * 100).toFixed(2)}%</td
          ><th>Sortino</th><td
            >{data.analytics.dist_stats.sortino?.toFixed(2)}</td
          ></tr
        >
        <tr
          ><th>Downside Dev</th><td
            >{(data.analytics.dist_stats.downside_dev * 100).toFixed(3)}%</td
          ><th></th><td></td></tr
        >
      </tbody>
    </table>
  </section>
{/if}

<section class="exports-all">
  <h3>Data Exports</h3>
  <div class="export-row">
    <button onclick={exportDaily} disabled={!data.returns}
      >Daily Returns CSV</button
    >
    <button
      onclick={exportMonthly}
      disabled={!data.analytics?.monthly_returns?.length}
      >Monthly Returns CSV</button
    >
    <button
      onclick={exportHistogram}
      disabled={!data.analytics?.return_histogram?.bins?.length}
      >Histogram CSV</button
    >
  </div>
</section>

<style>
  .crumbs {
    margin-bottom: 1rem;
  }
  .banner {
    padding: 0.75rem 1rem;
    background: rgba(248, 113, 113, 0.12);
    border: 1px solid rgba(248, 113, 113, 0.35);
    border-radius: 0.75rem;
    margin-bottom: 1.25rem;
  }
  .diag {
    margin: 0.6rem 0 0;
    background: rgba(2, 6, 23, 0.5);
    padding: 0.5rem 0.6rem;
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
    font-size: 0.65rem;
    max-height: 240px;
    overflow: auto;
  }
  .header {
    display: flex;
    justify-content: space-between;
    gap: 2rem;
    align-items: flex-start;
    margin-bottom: 2rem;
  }
  h2 {
    margin: 0 0 0.75rem;
  }
  .expr {
    margin: 0;
    padding: 0.75rem 1rem;
    background: rgba(2, 6, 23, 0.7);
    border: 1px solid rgba(30, 41, 59, 0.6);
    border-radius: 0.75rem;
    max-width: 680px;
    font-size: 0.85rem;
    white-space: pre-wrap;
  }
  .tags {
    list-style: none;
    display: flex;
    gap: 0.5rem;
    margin: 0.75rem 0 0;
    padding: 0;
  }
  .tags li {
    background: rgba(56, 189, 248, 0.2);
    color: #bae6fd;
    padding: 0.25rem 0.6rem;
    border-radius: 999px;
    font-size: 0.7rem;
  }
  .metrics {
    display: grid;
    gap: 0.75rem;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .metrics div {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(30, 41, 59, 0.6);
    padding: 0.6rem 0.75rem;
    border-radius: 0.65rem;
    display: flex;
    flex-direction: column;
  }
  .metrics span {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: rgba(148, 163, 184, 0.75);
  }
  .metrics strong {
    font-size: 0.95rem;
  }
  .chart-block,
  .returns-block {
    margin-bottom: 2.5rem;
  }
  .drawdown-block,
  .rolling-block {
    margin-bottom: 2.5rem;
  }
  .distribution-block,
  .monthly-block {
    margin-bottom: 2.5rem;
  }
  .stats-block,
  .exports-all {
    margin-bottom: 2.5rem;
  }
  .dd-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 0.75rem;
    font-size: 0.65rem;
  }
  .dd-table th,
  .dd-table td {
    padding: 0.4rem 0.5rem;
    text-align: right;
    border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  }
  .dd-table th {
    text-align: right;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    font-size: 0.55rem;
    color: rgba(148, 163, 184, 0.7);
  }
  .dd-table td:first-child,
  .dd-table th:first-child {
    text-align: center;
  }
  .dd-table td.neg {
    color: #f87171;
    font-variant-numeric: tabular-nums;
  }
  .rolling-grid {
    display: grid;
    gap: 1.5rem;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  }
  /* removed unused .spark styles */
  .analysis {
    margin-top: 1.25rem;
    display: grid;
    gap: 1rem;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    align-items: start;
  }
  .analysis h4 {
    margin: 0 0 0.4rem;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: rgba(148, 163, 184, 0.75);
  }
  .pill-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .pill-list li {
    background: rgba(56, 189, 248, 0.2);
    color: #bae6fd;
    padding: 0.25rem 0.55rem;
    border-radius: 0.5rem;
    font-size: 0.65rem;
    font-weight: 600;
  }
  .pill-list.alt li {
    background: rgba(129, 140, 248, 0.25);
    color: #c7d2fe;
  }
  .metrics-inline {
    display: flex;
    gap: 0.6rem;
    font-size: 0.65rem;
    align-items: center;
    flex-wrap: wrap;
  }
  .metrics-inline span {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(30, 41, 59, 0.6);
    padding: 0.25rem 0.5rem;
    border-radius: 0.45rem;
  }
  .empty {
    font-size: 0.65rem;
    color: rgba(148, 163, 184, 0.55);
  }
  .banner.warn {
    background: rgba(234, 179, 8, 0.12);
    border-color: rgba(234, 179, 8, 0.5);
  }
  .errs {
    margin: 0.5rem 0 0;
    padding-left: 1.1rem;
    font-size: 0.6rem;
  }
  .stats-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.65rem;
  }
  .stats-table th {
    text-align: left;
    padding: 0.3rem 0.4rem;
    font-weight: 600;
    color: rgba(148, 163, 184, 0.8);
  }
  .stats-table td {
    padding: 0.3rem 0.4rem;
    font-variant-numeric: tabular-nums;
  }
  .export-row {
    margin-top: 0.6rem;
    display: flex;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  button {
    background: #1e293b;
    border: 1px solid #334155;
    color: #e2e8f0;
    padding: 0.4rem 0.75rem;
    border-radius: 0.5rem;
    font-size: 0.6rem;
    cursor: pointer;
  }
  button:hover:enabled {
    background: #0f172a;
  }
  button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
</style>
