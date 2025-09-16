<script lang="ts">
  import type { PageData } from "./$types";
  import LineChart from "$lib/components/LineChart.svelte";
  import ReturnsBarChart from "$lib/components/ReturnsBarChart.svelte";
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
          points: data.equity.dates.map((d, i) => ({
            x: d,
            y: data.equity.equity[i],
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

<section class="returns-block">
  <h3>Daily Returns (last {data.returns?.returns.length} days)</h3>
  {#if data.returns}
    <ReturnsBarChart
      dates={data.returns.dates}
      values={data.returns.returns}
      height={140}
    />
  {:else}
    <p>No return data.</p>
  {/if}
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
  .spark {
    width: 100%;
    max-width: 640px;
    height: auto;
    stroke: #38bdf8;
    fill: none;
    stroke-width: 2;
  }
  .spark path {
    filter: drop-shadow(0 2px 4px rgba(56, 189, 248, 0.35));
  }
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
</style>
