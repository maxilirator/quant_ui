<script lang="ts">
  import type { PageData } from './$types';
  let { data }: { data: PageData } = $props();

  const formatPercent = (v: number) => `${(v * 100).toFixed(2)}%`;

  // Simple client-side sparkline path generator for equity curve
  let path = '';
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
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ');
  }
</script>

<svelte:head>
  <title>Strategy {data.strategy?.expr_hash} • Quant UI</title>
</svelte:head>

<nav class="crumbs"><a href="/strategies">← Strategies</a></nav>

{#if data.error}
  <div class="banner">{data.error}</div>
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
  </div>
  <div class="metrics">
    <div><span>Ann Return</span><strong>{formatPercent(data.strategy?.metrics.ann_return || 0)}</strong></div>
    <div><span>Vol</span><strong>{formatPercent(data.strategy?.metrics.ann_vol || 0)}</strong></div>
    <div><span>Sharpe</span><strong>{(data.strategy?.metrics.ann_sharpe || 0).toFixed(2)}</strong></div>
    <div><span>Max DD</span><strong>{formatPercent(data.strategy?.metrics.max_dd || 0)}</strong></div>
  </div>
</section>

<section class="chart-block">
  <h3>Equity Curve</h3>
  {#if path}
    <svg viewBox="0 0 320 80" class="spark"><path d={path} /></svg>
  {:else}
    <p>No equity data.</p>
  {/if}
</section>

<section class="returns-block">
  <h3>Daily Returns (last {data.returns?.returns.length} days)</h3>
  {#if data.returns}
    <div class="bars">
      {#each data.returns.returns as r, i}
        {#key i}
          <span class="bar" style={`--v:${r};`} title={`${data.returns.dates[i]}: ${formatPercent(r)}`}></span>
        {/key}
      {/each}
    </div>
  {:else}
    <p>No return data.</p>
  {/if}
</section>

<style>
  .crumbs { margin-bottom:1rem; }
  .banner { padding:0.75rem 1rem; background:rgba(248,113,113,0.12); border:1px solid rgba(248,113,113,0.35); border-radius:0.75rem; margin-bottom:1.25rem; }
  .header { display:flex; justify-content:space-between; gap:2rem; align-items:flex-start; margin-bottom:2rem; }
  h2 { margin:0 0 0.75rem; }
  .expr { margin:0; padding:0.75rem 1rem; background:rgba(2,6,23,0.7); border:1px solid rgba(30,41,59,0.6); border-radius:0.75rem; max-width:680px; font-size:0.85rem; white-space:pre-wrap; }
  .tags { list-style:none; display:flex; gap:0.5rem; margin:0.75rem 0 0; padding:0; }
  .tags li { background:rgba(56,189,248,0.2); color:#bae6fd; padding:0.25rem 0.6rem; border-radius:999px; font-size:0.7rem; }
  .metrics { display:grid; gap:0.75rem; grid-template-columns:repeat(2,minmax(0,1fr)); }
  .metrics div { background:rgba(15,23,42,0.6); border:1px solid rgba(30,41,59,0.6); padding:0.6rem 0.75rem; border-radius:0.65rem; display:flex; flex-direction:column; }
  .metrics span { font-size:0.65rem; text-transform:uppercase; letter-spacing:0.08em; color:rgba(148,163,184,0.75); }
  .metrics strong { font-size:0.95rem; }
  .chart-block, .returns-block { margin-bottom:2.5rem; }
  .spark { width:100%; max-width:640px; height:auto; stroke:#38bdf8; fill:none; stroke-width:2; }
  .spark path { filter: drop-shadow(0 2px 4px rgba(56,189,248,0.35)); }
  .bars { display:flex; align-items:flex-end; gap:2px; height:120px; max-width:640px; background:rgba(15,23,42,0.55); border:1px solid rgba(30,41,59,0.6); padding:0.5rem; border-radius:0.75rem; overflow:hidden; }
  .bar { flex:1; background:linear-gradient(180deg,#818cf8,#38bdf8); transform-origin:bottom; height:calc(60px + (var(--v) * 800px)); opacity:0.8; }
  .bar[style*='-'] { background:linear-gradient(180deg,#f87171,#fb923c); height:calc(60px + (var(--v) * -800px)); }
</style>
