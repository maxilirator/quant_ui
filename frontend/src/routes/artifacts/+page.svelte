<script lang="ts">
  import { onMount } from 'svelte';
  import { getArtifactManifest, listModelArtifacts, listReportArtifacts, listSignalArtifacts } from '$lib/api/client';

  export let data: { };
  let manifest: any = null;
  let models = [] as any[];
  let reports = [] as any[];
  let signals = [] as any[];
  let error: string | null = null;
  let loading = true;

  onMount(async () => {
    try {
      manifest = await getArtifactManifest(fetch);
      [models, reports, signals] = await Promise.all([
        listModelArtifacts(fetch),
        listReportArtifacts(fetch),
        listSignalArtifacts(fetch)
      ]);
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  });
</script>

<h1>Artifacts</h1>
{#if loading}
  <p>Loading artifacts…</p>
{:else if error}
  <p class="error">{error}</p>
{:else}
  <section>
    <h2>Manifest</h2>
    <p><code>generated_at:</code> {manifest.generated_at} | <code>git:</code> {manifest.git_commit} | <code>data_version:</code> {manifest.data_version}</p>
  </section>
  <section>
    <h2>Models ({models.length})</h2>
    {#if models.length === 0}<p>No models.</p>{/if}
    <ul>{#each models as m}<li>{m.file} <small>{m.sha256.slice(0,8)}…</small></li>{/each}</ul>
  </section>
  <section>
    <h2>Reports ({reports.length})</h2>
    {#if reports.length === 0}<p>No reports.</p>{/if}
    <ul>{#each reports as r}<li>{r.file}</li>{/each}</ul>
  </section>
  <section>
    <h2>Signals ({signals.length})</h2>
    {#if signals.length === 0}<p>No signals.</p>{/if}
    <ul>{#each signals as s}<li>{s.file}</li>{/each}</ul>
  </section>
{/if}

<style>
  h1 { margin-top: 0; }
  section { margin-bottom: 1.5rem; }
  ul { list-style: none; padding-left: 0; }
  li { font-family: monospace; }
  .error { color: #b00; }
</style>
