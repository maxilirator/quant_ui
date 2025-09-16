<script lang="ts">
  import type { PageData } from "./$types";
  let { data }: { data: PageData } = $props();
  let minReturn = $state();

  const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`;
  const sortOptions = [
    {
      label: "Return ↓ then Sharpe ↓",
      value: "ann_return_desc,ann_sharpe_desc",
    },
    { label: "Sharpe ↓", value: "ann_sharpe_desc" },
    { label: "Drawdown ↑ (shallow)", value: "max_dd_asc" },
    { label: "Newest", value: "created_at_desc" },
    { label: "Name A→Z", value: "expr_hash_asc" },
  ];
  // Loader already applied filters + order + pagination
  const f = data.filters || ({} as any);
  // Use a local variable for display; on change we trigger navigation explicitly.
  let currentOrder = $state<string>(data.order || "");

  function onOrderChange(e: Event) {
    const value = (e.target as HTMLSelectElement).value;
    // Build new URL with existing filters but updated order and reset page=1
    const params = new URLSearchParams();
    if (value) params.set("order", value);
    // preserve existing filled filters
    ["min_return", "max_vol", "min_sharpe", "max_dd", "created_after"].forEach(
      (k) => {
        const v = (f as any)[k];
        if (v) params.set(k, v);
      }
    );
    params.set("page", "1");
    const qs = params.toString();
    window.location.search = qs ? `?${qs}` : "";
  }
</script>

<svelte:head>
  <title>Strategies • Quant UI</title>
</svelte:head>

<section class="intro">
  <div class="header-col">
    <h2>Strategy library</h2>
    <p>Filter, sort and explore configured strategies.</p>
    <form class="filters" method="GET">
      <input type="hidden" name="page" value="1" />
      <div class="field-group">
        <label
          >Min Return
          <input
            name="min_return"
            type="number"
            step="0.0001"
            placeholder="0.05"
            bind:value={minReturn}
          />
        </label>
        <label
          >Max Vol
          <input
            name="max_vol"
            type="number"
            step="0.0001"
            placeholder="0.20"
            value={f.max_vol || ""}
          />
        </label>
        <label
          >Min Sharpe
          <input
            name="min_sharpe"
            type="number"
            step="0.01"
            placeholder="0.5"
            value={f.min_sharpe || ""}
          />
        </label>
        <label
          >Max DD
          <input
            name="max_dd"
            type="number"
            step="0.0001"
            placeholder="-0.10"
            value={f.max_dd || ""}
          />
        </label>
        <label
          >Created After
          <input
            name="created_after"
            type="date"
            value={f.created_after || ""}
          />
        </label>
        <label
          >Sort
          <select
            name="order"
            onchange={onOrderChange}
            bind:value={currentOrder}
          >
            <option value="">(default)</option>
            {#each sortOptions as opt}
              <option value={opt.value} selected={opt.value === currentOrder}
                >{opt.label}</option
              >
            {/each}
          </select>
        </label>
      </div>
      <div class="actions">
        <button type="submit">Apply</button>
        <a href="/strategies" class="reset">Reset</a>
      </div>
    </form>
  </div>
  <div class="meta">
    <small class="page-meta">Page {data.page} / {data.totalPages}</small>
    <nav class="pager">
      {#if data.prevHref}
        <a class="page-btn" href={data.prevHref} rel="prev">← Prev</a>
      {:else}
        <span class="page-btn disabled">← Prev</span>
      {/if}
      {#if data.nextHref}
        <a class="page-btn" href={data.nextHref} rel="next">Next →</a>
      {:else}
        <span class="page-btn disabled">Next →</span>
      {/if}
    </nav>
    <small class="page-meta"
      >Showing {data.strategies.length} of {data.total}</small
    >
  </div>
</section>

{#if data.error}
  <div class="banner" role="status">
    <strong>{data.error}</strong>
    {#if data.diagnostics?.detail}
      <pre class="diag">{JSON.stringify(data.diagnostics.detail, null, 2)}</pre>
    {:else if data.diagnostics}
      <pre class="diag">{JSON.stringify(data.diagnostics, null, 2)}</pre>
    {/if}
  </div>
{/if}

{#if data.strategies.length === 0}
  <p class="empty">
    No strategies available yet. Launch a training job to populate the
    catalogue.
  </p>
{:else}
  <div class="grid">
    {#each data.strategies as strategy (strategy.expr_hash)}
      <article class="card">
        <header>
          <div class="title-block">
            <h3 title={strategy.expr_hash}>
              <a
                class="hash-link truncate"
                href={`/strategies/${strategy.expr_hash}`}
                >{strategy.expr_hash}</a
              >
            </h3>
            {#if strategy.tags?.length}
              <ul class="tags">
                {#each strategy.tags as tag}
                  <li>{tag}</li>
                {/each}
              </ul>
            {/if}
          </div>
          <span class="score" title="Complexity score"
            >{strategy.complexity_score.toFixed(1)}</span
          >
        </header>
        <details class="expr-wrapper">
          <summary title="Click to expand full DSL expression">
            <code class="expr-line">{strategy.expr}</code>
          </summary>
          <pre class="expr-full" aria-label="Expression">{strategy.expr}</pre>
        </details>
        <dl class="metrics">
          <div>
            <dt>Annual return</dt>
            <dd>{formatPercent(strategy.metrics.ann_return)}</dd>
          </div>
          <div>
            <dt>Volatility</dt>
            <dd>{formatPercent(strategy.metrics.ann_vol)}</dd>
          </div>
          <div>
            <dt>Sharpe</dt>
            <dd>{strategy.metrics.ann_sharpe.toFixed(2)}</dd>
          </div>
          <div>
            <dt>Max drawdown</dt>
            <dd>{formatPercent(strategy.metrics.max_dd)}</dd>
          </div>
        </dl>
        {#if strategy.notes}
          <p class="notes">{strategy.notes}</p>
        {/if}
        <footer>
          <small>Created {new Date(strategy.created_at).toLocaleString()}</small
          >
        </footer>
      </article>
    {/each}
  </div>
{/if}

<details class="debug debug-panel">
  <summary>Debug (loader)</summary>
  <pre>{JSON.stringify(data.debug, null, 2)}</pre>
</details>

<style>
  .intro {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 2rem;
    margin-bottom: 2rem;
  }
  .header-col {
    flex: 1;
    min-width: 520px;
  }
  form.filters {
    margin-top: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .field-group {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
  }
  .field-group label {
    display: flex;
    flex-direction: column;
    font-size: 0.6rem;
    gap: 0.25rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: rgba(148, 163, 184, 0.75);
  }
  .field-group input,
  .field-group select {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(71, 85, 105, 0.5);
    color: #f1f5f9;
    padding: 0.45rem 0.55rem;
    border-radius: 0.5rem;
    font-size: 0.7rem;
    min-width: 110px;
  }
  /* Remove number input arrows */
  .field-group input[type="number"]::-webkit-inner-spin-button,
  .field-group input[type="number"]::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }
  .field-group input[type="number"] {
    appearance: textfield;
    -moz-appearance: textfield;
  }
  .actions {
    display: flex;
    gap: 0.6rem;
  }
  .actions button {
    background: #0ea5e9;
    color: #f8fafc;
    border: none;
    padding: 0.55rem 0.9rem;
    border-radius: 0.55rem;
    font-size: 0.7rem;
    cursor: pointer;
  }
  .actions button:hover {
    background: #0284c7;
  }
  .actions .reset {
    font-size: 0.65rem;
    color: #94a3b8;
    text-decoration: none;
    align-self: center;
  }
  .actions .reset:hover {
    text-decoration: underline;
  }

  .intro h2 {
    margin: 0 0 0.75rem;
    font-size: 2rem;
  }

  .intro p {
    margin: 0;
    color: rgba(226, 232, 240, 0.78);
    line-height: 1.6;
  }

  .meta {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.5rem;
  }

  .pager {
    display: flex;
    gap: 0.4rem;
  }

  .page-btn {
    font-size: 0.7rem;
    padding: 0.35rem 0.65rem;
    border-radius: 0.45rem;
    background: rgba(71, 85, 105, 0.35);
    color: #f1f5f9;
    text-decoration: none;
    line-height: 1;
  }

  .page-btn:hover {
    background: rgba(71, 85, 105, 0.55);
  }

  .page-btn.disabled {
    opacity: 0.35;
    pointer-events: none;
  }

  .page-meta {
    font-size: 0.6rem;
    color: rgba(148, 163, 184, 0.75);
  }

  /* removed unused .count and .fallback selectors */

  .banner {
    padding: 0.85rem 1.1rem;
    border-radius: 0.75rem;
    background: rgba(248, 113, 113, 0.12);
    border: 1px solid rgba(248, 113, 113, 0.35);
    color: #fecaca;
    margin-bottom: 1.5rem;
  }
  .diag {
    margin: 0.75rem 0 0;
    background: rgba(2, 6, 23, 0.4);
    padding: 0.6rem 0.75rem;
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.5rem;
    color: #f1f5f9;
    font-size: 0.7rem;
    max-height: 260px;
    overflow: auto;
  }

  .empty {
    text-align: center;
    color: rgba(148, 163, 184, 0.85);
    padding: 3rem 0;
  }

  .grid {
    display: grid;
    gap: 1.75rem;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 1.1rem;
    padding: 1.75rem;
    background: rgba(15, 23, 42, 0.7);
    border: 1px solid rgba(71, 85, 105, 0.45);
    border-radius: 1rem;
    box-shadow: inset 0 1px 0 rgba(148, 163, 184, 0.12);
  }

  .card header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
  }

  .card h3 {
    margin: 0;
    font-size: 1.2rem;
  }

  .title-block {
    max-width: 100%;
  }
  .truncate {
    display: inline-block;
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    vertical-align: bottom;
  }

  .hash-link {
    color: #f1f5f9;
    text-decoration: none;
  }

  .hash-link:hover {
    text-decoration: underline;
  }

  .tags {
    display: flex;
    gap: 0.5rem;
    padding: 0;
    margin: 0.35rem 0 0;
    list-style: none;
  }

  .tags li {
    font-size: 0.75rem;
    padding: 0.2rem 0.6rem;
    border-radius: 999px;
    background: rgba(56, 189, 248, 0.2);
    color: #bae6fd;
  }

  .score {
    font-weight: 700;
    font-size: 1.1rem;
    background: rgba(56, 189, 248, 0.18);
    color: #f8fafc;
    padding: 0.35rem 0.7rem;
    border-radius: 0.75rem;
  }

  .expr-wrapper {
    margin: 0;
    padding: 0.55rem 0.75rem;
    border-radius: 0.65rem;
    background: rgba(2, 6, 23, 0.6);
    border: 1px solid rgba(30, 41, 59, 0.6);
    font-size: 0.75rem;
  }
  .expr-wrapper summary {
    list-style: none;
    cursor: pointer;
    outline: none;
  }
  .expr-wrapper summary::-webkit-details-marker {
    display: none;
  }
  .expr-line {
    display: inline-block;
    max-width: 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .expr-full {
    margin: 0.6rem 0 0;
    padding: 0.6rem 0.7rem;
    background: rgba(2, 6, 23, 0.85);
    border: 1px solid rgba(30, 41, 59, 0.55);
    border-radius: 0.55rem;
    font-size: 0.7rem;
    max-height: 180px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .metrics {
    display: grid;
    gap: 0.75rem;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin: 0;
  }

  .metrics div {
    background: rgba(15, 23, 42, 0.6);
    border-radius: 0.65rem;
    padding: 0.75rem;
    border: 1px solid rgba(30, 41, 59, 0.6);
  }

  .metrics dt {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: rgba(148, 163, 184, 0.85);
    margin-bottom: 0.25rem;
  }

  .metrics dd {
    margin: 0;
    font-size: 0.95rem;
    font-weight: 600;
  }

  .notes {
    margin: 0;
    color: rgba(226, 232, 240, 0.75);
    line-height: 1.5;
  }

  footer {
    margin-top: auto;
    color: rgba(148, 163, 184, 0.7);
  }
  .debug-panel {
    margin-top: 2rem;
    background: rgba(2, 6, 23, 0.5);
    border: 1px solid rgba(71, 85, 105, 0.4);
    padding: 1rem 1.25rem;
    border-radius: 0.75rem;
    font-size: 0.65rem;
    max-height: 300px;
    overflow: auto;
  }
  details.debug summary {
    cursor: pointer;
    font-size: 0.7rem;
    color: #38bdf8;
  }
</style>
