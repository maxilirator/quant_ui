<script lang="ts">
  import { onMount } from 'svelte';
  import { getPanelSlice } from '$lib/api/client';

  let start = '';
  let end = '';
  let tickers = '';
  let loading = false;
  let rows: any[] = [];
  let columns: string[] = [];
  let meta: { total_rows: number; downsampled: boolean } | null = null;
  let error: string | null = null;

  async function load() {
    loading = true; error = null;
    try {
      const params: any = {};
      if (start) params.start = start;
      if (end) params.end = end;
      if (tickers) params.tickers = tickers.split(',').map(t => t.trim()).filter(Boolean);
      const res = await getPanelSlice(fetch, params);
      rows = res.rows; columns = res.columns; meta = { total_rows: res.total_rows, downsampled: res.downsampled };
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  onMount(load);
</script>

<h1>Panel Slice</h1>
<form on:submit|preventDefault={load} class="controls">
  <label>Start <input bind:value={start} placeholder="YYYY-MM-DD" /></label>
  <label>End <input bind:value={end} placeholder="YYYY-MM-DD" /></label>
  <label>Tickers <input bind:value={tickers} placeholder="ERIC,SEB" /></label>
  <button type="submit" disabled={loading}>Load</button>
</form>

{#if loading}
  <p>Loading…</p>
{:else if error}
  <p class="error">{error}</p>
{:else if rows.length === 0}
  <p>No rows.</p>
{:else}
  <p><strong>{meta.total_rows}</strong> total rows {#if meta.downsampled}(downsampled){/if}</p>
  <div class="table-wrapper">
    <table>
      <thead><tr>{#each columns as c}<th>{c}</th>{/each}</tr></thead>
      <tbody>
        {#each rows.slice(0,500) as r}
          <tr>{#each columns as c}<td>{r[c]}</td>{/each}</tr>
        {/each}
      </tbody>
    </table>
    {#if rows.length > 500}<p>Showing first 500 rows.</p>{/if}
  </div>
{/if}

<style>
  form.controls { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem; }
  label { font-size: 0.85rem; display: flex; flex-direction: column; }
  input { padding: 0.25rem 0.5rem; }
  table { border-collapse: collapse; width: 100%; font-size: 0.8rem; }
  th, td { border: 1px solid #ddd; padding: 2px 4px; white-space: nowrap; }
  thead { background: #f5f5f5; position: sticky; top: 0; }
  .table-wrapper { max-height: 400px; overflow: auto; border: 1px solid #ddd; }
  .error { color: #b00; }
</style>
