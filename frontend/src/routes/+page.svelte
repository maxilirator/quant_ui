<script lang="ts">
  import { getReadinessDiagnostics } from "$lib/api/client";
  interface Suggestion {
    check_id: string;
    tasks: string[];
    status: string;
  }
  interface Summary {
    status: string;
    fail_count: number;
    warn_count: number;
    generated_at: number;
    params?: any;
    suggestions?: Suggestion[];
  }
  interface Check {
    id: string;
    status: string;
    message: string;
    remediation?: string;
    metrics?: Record<string, any>;
    category?: string;
  }
  let summary: Summary | null = null;
  let checks: Check[] = [];
  let expanded: Record<string, boolean> = {};
  let loading = false;
  let error: string | null = null;
  let params = { min_tickers: 50, min_days: 500, fresh_days: 5 };
  async function refresh() {
    loading = true;
    error = null;
    try {
      const r = await getReadinessDiagnostics(fetch, params);
      summary = r.summary;
      checks = r.checks.map((c) => ({
        id: c.id,
        status: c.status,
        message: c.message,
        remediation: c.remediation,
        metrics: c.metrics,
        category: c.category,
      }));
    } catch (e: any) {
      error = e.message || String(e);
    } finally {
      loading = false;
    }
  }
  refresh();
</script>

<svelte:head>
  <title>Quant UI Overview</title>
</svelte:head>

<section class="hero">
  <h2>Quant research control centre</h2>
  <p>
    This skeleton stitches together a SvelteKit interface with the FastAPI
    surface described in the architecture brief. Use it to iterate on
    interaction flows, data visualisations, and live job updates while the
    quant-core contracts are stabilised.
  </p>
  <div class="actions">
    <a class="primary" href="/strategies">Browse strategies</a>
    <a
      class="secondary"
      href="/ARCHITECTURE_UI.md"
      target="_blank"
      rel="noreferrer">Read architecture</a
    >
  </div>
</section>

<section class="grid">
  <article class="readiness">
    <h3>Environment Readiness</h3>
    <div class="readiness-top">
      <div class="badge" data-status={summary?.status || "unknown"}>
        {#if loading}Loading...{:else if error}Error{:else if summary}{summary.status.toUpperCase()}
          F:{summary.fail_count} W:{summary.warn_count}{:else}—{/if}
      </div>
      <div class="controls">
        <label
          >tickers <input
            type="number"
            bind:value={params.min_tickers}
            min="1"
          /></label
        >
        <label
          >days <input
            type="number"
            bind:value={params.min_days}
            min="1"
          /></label
        >
        <label
          >fresh <input
            type="number"
            bind:value={params.fresh_days}
            min="0"
          /></label
        >
        <button on:click={refresh} disabled={loading}>Refresh</button>
      </div>
    </div>
    {#if error}<div class="err">{error}</div>{/if}
    {#if checks.length}
      {#if summary?.suggestions?.length}
        <div class="suggestions">
          <strong>Suggestions for fixes:</strong>
          {#each summary.suggestions as s}
            <a
              class="suggest-chip {s.status}"
              href={`/control?task=${s.tasks[0]}`}
              title={`Tasks: ${s.tasks.join(", ")}`}
              >{s.check_id} » {s.tasks[0]}</a
            >
          {/each}
        </div>
      {/if}
      <table class="r-table">
        <thead
          ><tr
            ><th></th><th>ID</th><th>Status</th><th>Message</th><th>Category</th
            ></tr
          ></thead
        >
        <tbody>
          {#each checks as c}
            <tr class={c.status}>
              <td class="exp-cell"
                ><button
                  class="exp"
                  on:click={() => (expanded[c.id] = !expanded[c.id])}
                  aria-label="toggle details"
                  >{expanded[c.id] ? "−" : "+"}</button
                ></td
              >
              <td>{c.id}</td>
              <td>{c.status}</td>
              <td>{c.message}</td>
              <td>{c.category || ""}</td>
            </tr>
            {#if expanded[c.id]}
              <tr class="details-row">
                <td></td>
                <td colspan="4">
                  <div class="detail-block">
                    {#if c.remediation && c.remediation !== "None"}<div
                        class="remed"
                      >
                        <strong>Remediation:</strong>
                        {c.remediation}
                      </div>{/if}
                    {#if c.metrics}
                      <div class="metrics">
                        {#each Object.entries(c.metrics) as m (m[0])}
                          {#if typeof m[1] === "object" && m[1] !== null && Array.isArray(m[1])}
                            {#if m[1].length && typeof m[1][0] === "object"}
                              <details>
                                <summary>{m[0]} ({m[1].length})</summary>
                                <table class="mini">
                                  <thead>
                                    <tr>
                                      {#each Object.keys(m[1][0]) as col}<th
                                          >{col}</th
                                        >{/each}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {#each m[1] as row}
                                      <tr
                                        >{#each Object.keys(m[1][0]) as col}<td
                                            >{row[col]}</td
                                          >{/each}</tr
                                      >
                                    {/each}
                                  </tbody>
                                </table>
                              </details>
                            {:else}
                              <div class="kv">
                                <span>{m[0]}:</span>
                                {JSON.stringify(m[1])}
                              </div>
                            {/if}
                          {:else if typeof m[1] === "object" && m[1] !== null}
                            <details>
                              <summary>{m[0]}</summary>
                              <pre>{JSON.stringify(m[1], null, 2)}</pre>
                            </details>
                          {:else}
                            <div class="kv">
                              <span>{m[0]}:</span>
                              {String(m[1])}
                            </div>
                          {/if}
                        {/each}
                      </div>
                    {/if}
                  </div>
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
      <p class="tiny">Detailed remediation available on Control page.</p>
    {/if}
  </article>
</section>

<style>
  .hero {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 1.25rem;
    :global(.r-table th) {
      text-align: left;
    }
    :global(.exp-cell) {
      width: 26px;
    }
    :global(button.exp) {
      background: #1e293b;
      color: #e2e8f0;
      border: 1px solid #334155;
      width: 22px;
      height: 22px;
      line-height: 1;
      font-size: 0.75rem;
      border-radius: 4px;
      cursor: pointer;
    }
    :global(button.exp:hover) {
      background: #0f172a;
    }
    padding: 2.5rem;
    box-shadow: 0 30px 80px rgba(15, 23, 42, 0.45);
    margin-bottom: 3rem;
  }

  .hero h2 {
    font-size: 2.2rem;
    margin-top: 0;
    margin-bottom: 1rem;
  }

  .hero p {
    margin: 0;
    line-height: 1.7;
    color: rgba(226, 232, 240, 0.8);
    :global(.details-row td) {
      background: #0f172a;
      font-size: 0.75rem;
    }
    :global(.detail-block) {
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
    }
    :global(.remed) {
      font-size: 0.75rem;
      color: #fbbf24;
    }
    :global(.metrics) {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }
    :global(.kv) {
      font-size: 0.7rem;
      display: flex;
      gap: 4px;
    }
    :global(.kv span) {
      font-weight: 600;
    }
    :global(table.mini) {
      width: auto;
      border-collapse: collapse;
      margin-top: 4px;
      font-size: 0.6rem;
    }
    :global(table.mini th),
    :global(table.mini td) {
      border: 1px solid #334155;
      padding: 2px 4px;
    }
    :global(.suggestions) {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      margin: 0.4rem 0;
    }
    :global(.suggest-chip) {
      font-size: 0.6rem;
      padding: 4px 8px;
      border-radius: 14px;
      text-decoration: none;
      background: #1e293b;
      border: 1px solid #334155;
      color: #e2e8f0;
    }
    :global(.suggest-chip.fail) {
      border-color: #fb7185;
    }
    :global(.suggest-chip.warn) {
      border-color: #fbbf24;
    }
    :global(.suggest-chip:hover) {
      background: #0f172a;
    }
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-top: 2rem;
  }

  .primary,
  .secondary {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.85rem 1.6rem;
    border-radius: 9999px;
    font-weight: 600;
    transition:
      transform 160ms ease,
      box-shadow 160ms ease;
  }

  .primary {
    background: linear-gradient(135deg, #38bdf8, #818cf8);
    color: #0f172a;
    box-shadow: 0 20px 40px rgba(56, 189, 248, 0.35);
  }

  .primary:hover {
    transform: translateY(-1px);
  }

  .secondary {
    border: 1px solid rgba(148, 163, 184, 0.4);
    color: rgba(226, 232, 240, 0.9);
  }

  .secondary:hover {
    transform: translateY(-1px);
    box-shadow: 0 14px 30px rgba(148, 163, 184, 0.2);
  }

  .grid {
    display: grid;
    gap: 1.75rem;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }

  .grid article {
    padding: 1.75rem;
    border-radius: 1rem;
    background: rgba(15, 23, 42, 0.55);
    border: 1px solid rgba(71, 85, 105, 0.45);
    box-shadow: inset 0 1px 0 rgba(148, 163, 184, 0.1);
  }

  .grid h3 {
    margin-top: 0;
    margin-bottom: 0.75rem;
  }

  .grid p {
    margin: 0;
    color: rgba(226, 232, 240, 0.75);
    line-height: 1.6;
  }
  .readiness {
    position: relative;
  }
  .readiness-top {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    flex-wrap: wrap;
  }
  .controls {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    font-size: 0.65rem;
  }
  .controls label {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .controls input {
    width: 60px;
    background: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding: 4px 6px;
  }
  .controls button {
    background: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding: 4px 12px;
    font-size: 0.75rem;
    border-radius: 6px;
    cursor: pointer;
  }
  .suggestions {
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
    line-height: 2.1rem;
    border: #334155 solid 1px;
    border-radius: 0.5rem;
    padding: 0.5rem;
    background: #0f172a;
    color: #e2e8f0;
  }
  .suggestions a {
    padding: 4px 8px;
    margin: 2px;
    border-radius: 0.5rem;
    background: #1e293b;
    border: #1e2a47 solid 1px;
    text-decoration: none;
    color: #38bdf8;
  }
  .suggestions a:hover {
    color: #69c5ec;
    background: #324563;
  }
  .badge {
    font-size: 0.7rem;
    padding: 4px 10px;
    border-radius: 18px;
    background: #1e293b;
  }
  .badge[data-status="fail"] {
    background: #4c0519;
    color: #fb7185;
  }
  .badge[data-status="warn"] {
    background: #713f12;
    color: #fbbf24;
  }
  .badge[data-status="ok"] {
    background: #064e3b;
    color: #34d399;
  }
  .r-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 1rem;
    margin-top: 0.5rem;
  }
  .r-table th,
  .r-table td {
    padding: 4px 6px;
    border-bottom: 1px solid #334155;
  }
  .r-table tr.fail td {
    background: #2d0f1a;
  }
  .r-table tr.warn td {
    background: #2d210f;
  }
  .r-table tr.pass td {
    background: #10291f;
  }
  .tiny {
    font-size: 0.9rem;
    opacity: 0.7;
    margin-top: 0.4rem;
  }
  .err {
    color: #f87171;
    font-size: 0.65rem;
  }
</style>
