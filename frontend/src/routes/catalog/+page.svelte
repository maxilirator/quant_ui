<script lang="ts">
  import type { PageData } from './$types';
  let { data }: { data: PageData } = $props();
</script>

<svelte:head>
  <title>Catalog • Quant UI</title>
</svelte:head>

<section class="intro">
  <div>
    <h2>Unified Catalog</h2>
    <p>
      Aggregated view of quantitative building blocks discovered from the connected quant-core and artifacts manifest.
      Falls back to stub data when the backend is offline.
    </p>
  </div>
  <div class="meta">
    <span class="count">{data.features.length} features</span>
    <span class="count">{data.primitives.length} primitives</span>
    <span class="count">{Object.keys(data.artifactCounts || {}).length} artifact kinds</span>
    {#if data.usingFallback}
      <span class="fallback">Offline mode</span>
    {/if}
    {#if data.aggregated}
      <span class="aggregated" title="Loaded via /catalog/manifest">Aggregated</span>
    {/if}
  </div>
</section>

{#if data.error}
  <div class="banner">{data.error}</div>
{/if}

<div class="summary-grid">
  <div class="panel">
    <h3>Artifact Kinds</h3>
    {#if Object.keys(data.artifactCounts).length === 0}
      <p class="empty">No artifact manifest data.</p>
    {:else}
      <ul class="kv">
        {#each Object.entries(data.artifactCounts) as [k, v]}
          <li><span>{k}</span><strong>{v}</strong></li>
        {/each}
      </ul>
    {/if}
  </div>
  <div class="panel">
    <h3>Strategy Tags</h3>
    {#if data.strategyTagStats.length === 0}
      <p class="empty">No tag stats.</p>
    {:else}
      <ul class="tags-cloud">
        {#each data.strategyTagStats as t}
          <li style={`--w:${Math.min(1, 0.4 + t.count / (data.strategyTagStats[0].count || 1))}`}>{t.tag}<small>{t.count}</small></li>
        {/each}
      </ul>
    {/if}
  </div>
  <div class="panel">
    <h3>Datasets</h3>
    {#if data.datasets.length === 0}
      <p class="empty">No dataset artifacts.</p>
    {:else}
      <ul class="datasets">
        {#each data.datasets as d}
          <li title={d.file}><code>{d.file}</code><small>{(d.size/1024).toFixed(1)} KB</small></li>
        {/each}
      </ul>
    {/if}
  </div>
</div>

<div class="split">
  <div>
    <h3>Features</h3>
    <ul class="list">
      {#each data.features as f}
        <li>
          <strong>{f.name}</strong>
          <small class="group">[{f.group}]</small>
          <div class="desc">{f.description}</div>
        </li>
      {/each}
    </ul>
  </div>
  <div>
    <h3>Primitives</h3>
    <ul class="list">
      {#each data.primitives as p}
        <li>
          <strong>{p.name}</strong>
          <small class="group">[{p.category}]</small>
          <div class="desc">{p.description}</div>
          <small class="arity">arity: {p.arity}</small>
        </li>
      {/each}
    </ul>
  </div>
</div>

<style>
  .intro { display:flex; justify-content:space-between; gap:2rem; margin-bottom:2rem; }
  .meta { display:flex; flex-direction:column; align-items:flex-end; gap:0.5rem; }
  .count { background:rgba(148,163,184,0.2); padding:0.35rem 0.8rem; border-radius:999px; font-weight:600; }
  .fallback { font-size:0.75rem; text-transform:uppercase; letter-spacing:0.08em; color:#fbbf24; }
  .aggregated { font-size:0.65rem; text-transform:uppercase; letter-spacing:0.08em; background:rgba(56,189,248,0.2); color:#38bdf8; padding:0.25rem 0.55rem; border-radius:0.5rem; }
  .banner { padding:0.75rem 1rem; background:rgba(248,113,113,0.12); border:1px solid rgba(248,113,113,0.35); border-radius:0.75rem; margin-bottom:1.5rem; }
  .summary-grid { display:grid; gap:1.5rem; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); margin-bottom:2.5rem; }
  .panel { background:rgba(15,23,42,0.6); border:1px solid rgba(71,85,105,0.45); border-radius:0.75rem; padding:1rem 1.1rem; }
  .panel h3 { margin-top:0; margin-bottom:0.85rem; }
  .kv { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:0.45rem; }
  .kv li { display:flex; justify-content:space-between; align-items:center; font-size:0.9rem; }
  .kv span { color:rgba(148,163,184,0.75); }
  .kv strong { font-weight:600; }
  .empty { color:rgba(148,163,184,0.65); font-size:0.8rem; }
  .tags-cloud { list-style:none; margin:0; padding:0; display:flex; flex-wrap:wrap; gap:0.5rem; }
  .tags-cloud li { background:rgba(56,189,248,0.15); color:#bae6fd; padding:0.35rem 0.6rem; border-radius:0.6rem; font-size:0.65rem; display:inline-flex; align-items:center; gap:0.35rem; font-weight:600; transform:scale(var(--w,1)); }
  .tags-cloud small { font-size:0.55rem; opacity:0.8; }
  .datasets { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:0.4rem; max-height:180px; overflow:auto; }
  .datasets li { display:flex; justify-content:space-between; gap:1rem; font-size:0.7rem; background:rgba(2,6,23,0.5); border:1px solid rgba(30,41,59,0.6); padding:0.4rem 0.55rem; border-radius:0.45rem; }
  .datasets code { color:#f1f5f9; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:160px; }
  .datasets small { color:rgba(148,163,184,0.7); }
  .split { display:grid; gap:2rem; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); }
  h3 { margin-top:0; }
  .list { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:1rem; }
  .list li { background:rgba(15,23,42,0.6); border:1px solid rgba(71,85,105,0.45); border-radius:0.75rem; padding:0.9rem 1rem; }
  .group { color:rgba(148,163,184,0.7); margin-left:0.4rem; }
  .desc { color:rgba(226,232,240,0.75); font-size:0.85rem; margin-top:0.25rem; }
  .arity { color:rgba(148,163,184,0.55); font-size:0.7rem; text-transform:uppercase; letter-spacing:0.08em; }
</style>
