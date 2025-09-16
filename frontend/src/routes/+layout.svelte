<script lang="ts">
  import favicon from '$lib/assets/favicon.svg';

  let { children } = $props();
</script>

<svelte:head>
  <link rel="icon" href={favicon} />
  <title>Quant UI</title>
</svelte:head>

<div class="app-shell">
  <header class="app-header">
    <div class="brand">
      <span class="logo">Q</span>
      <div>
        <h1>Quant UI</h1>
        <p>Research &amp; backtest console</p>
      </div>
    </div>
    <nav>
      <a href="/">Overview</a>
      <a href="/strategies">Strategies</a>
      <a href="/catalog">Catalog</a>
      <a href="/panel">Panel</a>
      <a href="/artifacts">Artifacts</a>
    </nav>
  </header>
  <main>
    {@render children?.()}
  </main>
  <footer>
    <small>Skeleton build – connect the FastAPI backend to unlock live strategy analytics.</small>
  </footer>
</div>

<style>
  :global(body) {
    margin: 0;
    font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: radial-gradient(circle at top left, #0f172a 0%, #020617 55%, #000 100%);
    color: #e2e8f0;
    min-height: 100vh;
  }

  a {
    color: #38bdf8;
    text-decoration: none;
  }

  a:hover {
    text-decoration: underline;
  }

  .app-shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  .app-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem 2.5rem;
    background: rgba(15, 23, 42, 0.9);
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    backdrop-filter: blur(8px);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .brand h1 {
    margin: 0;
    font-size: 1.5rem;
    letter-spacing: 0.04em;
  }

  .brand p {
    margin: 0;
    font-size: 0.9rem;
    color: rgba(226, 232, 240, 0.7);
  }

  .logo {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 0.75rem;
    background: linear-gradient(135deg, #38bdf8, #818cf8);
    color: #0f172a;
    font-weight: 700;
    font-size: 1.25rem;
    box-shadow: 0 10px 30px rgba(56, 189, 248, 0.45);
  }

  nav a {
    margin-left: 1.5rem;
    font-weight: 600;
    color: rgba(226, 232, 240, 0.85);
  }

  nav a:hover {
    color: #f8fafc;
  }

  main {
    flex: 1;
    padding: 2.5rem;
    max-width: 1080px;
    width: 100%;
    margin: 0 auto;
    box-sizing: border-box;
  }

  footer {
    padding: 1.25rem;
    text-align: center;
    font-size: 0.85rem;
    color: rgba(226, 232, 240, 0.6);
    border-top: 1px solid rgba(148, 163, 184, 0.2);
  }
</style>
