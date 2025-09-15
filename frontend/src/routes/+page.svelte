<svelte:head>
  <title>Quant UI Overview</title>
</svelte:head>

<section class="hero">
  <h2>Quant research control centre</h2>
  <p>
    This skeleton stitches together a SvelteKit interface with the FastAPI surface described in the architecture brief. Use it to
    iterate on interaction flows, data visualisations, and live job updates while the quant-core contracts are stabilised.
  </p>
  <div class="actions">
    <a class="primary" href="/strategies">Browse strategies</a>
    <a class="secondary" href="/ARCHITECTURE_UI.md" target="_blank" rel="noreferrer">Read architecture</a>
  </div>
</section>

<section class="grid">
  <article>
    <h3>Comprehensive API coverage</h3>
    <p>
      Every endpoint from the roadmap is represented in the FastAPI service with strongly typed schemas. Swap the placeholder data
      for real persistence or quant-core adapters without changing the request boundaries.
    </p>
  </article>
  <article>
    <h3>Live job telemetry</h3>
    <p>
      The backend exposes job list, detail, log, and websocket stream routes so that the UI can display progress bars and event
      timelines for both training runs and ad-hoc backtests.
    </p>
  </article>
  <article>
    <h3>UI ready for analytics</h3>
    <p>
      The `/strategies` route demonstrates how data contracts flow into interactive cards. Replace the stub fetcher with real API
      calls and enhance the layout with charts, filters, and broker integrations.
    </p>
  </article>
</section>

<style>
  .hero {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 1.25rem;
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
    transition: transform 160ms ease, box-shadow 160ms ease;
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
</style>
