<script lang="ts">
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();

  const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`;
</script>

<svelte:head>
  <title>Strategies • Quant UI</title>
</svelte:head>

<section class="intro">
  <div>
    <h2>Strategy library</h2>
    <p>
      Inspect placeholder strategies returned by the FastAPI skeleton. Wire in the real quant-core service to surface live
      metrics, equity curves, and broker links.
    </p>
  </div>
  <div class="meta">
    <span class="count">{data.total} strategies</span>
    {#if data.usingFallback}
      <span class="fallback">Offline mode</span>
    {/if}
  </div>
</section>

{#if data.error}
  <div class="banner" role="status">{data.error}</div>
{/if}

{#if data.strategies.length === 0}
  <p class="empty">No strategies available yet. Launch a training job to populate the catalogue.</p>
{:else}
  <div class="grid">
    {#each data.strategies as strategy}
      <article class="card">
        <header>
          <div>
            <h3>{strategy.expr_hash}</h3>
            {#if strategy.tags?.length}
              <ul class="tags">
                {#each strategy.tags as tag}
                  <li>{tag}</li>
                {/each}
              </ul>
            {/if}
          </div>
          <span class="score" title="Complexity score">{strategy.complexity_score.toFixed(1)}</span>
        </header>
        <pre class="expr" aria-label="Expression">{strategy.expr}</pre>
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
          <small>Created {new Date(strategy.created_at).toLocaleString()}</small>
        </footer>
      </article>
    {/each}
  </div>
{/if}

<style>
  .intro {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 2rem;
    margin-bottom: 2rem;
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

  .count {
    font-weight: 600;
    background: rgba(148, 163, 184, 0.2);
    padding: 0.35rem 0.8rem;
    border-radius: 999px;
  }

  .fallback {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #fbbf24;
  }

  .banner {
    padding: 0.85rem 1.1rem;
    border-radius: 0.75rem;
    background: rgba(248, 113, 113, 0.12);
    border: 1px solid rgba(248, 113, 113, 0.35);
    color: #fecaca;
    margin-bottom: 1.5rem;
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

  .expr {
    margin: 0;
    padding: 0.9rem;
    border-radius: 0.75rem;
    background: rgba(2, 6, 23, 0.7);
    border: 1px solid rgba(30, 41, 59, 0.6);
    font-family: 'Fira Code', 'SFMono-Regular', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
      'Courier New', monospace;
    font-size: 0.85rem;
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
</style>
