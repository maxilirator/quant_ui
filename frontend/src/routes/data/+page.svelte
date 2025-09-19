<script lang="ts">
  import { onMount } from "svelte";
  import {
    listDataDomains,
    getDomainSample,
    listDataFiles,
    previewDataFile,
    type DomainsResponse,
    type DomainMeta,
    type DomainSample,
    type DataFileEntry,
    type FilePreview,
  } from "$lib/api/client";

  let domains: DomainMeta[] = [];
  let skipped: { domain?: string; reason?: string }[] = [];
  let selectedDomain: string | null = null;
  let domainSample: DomainSample | null = null;
  let sampleLimit = 50;
  let loadingSample = false;
  let files: DataFileEntry[] = [];
  let fileFilter = "";
  let selectedFile: DataFileEntry | null = null;
  let filePreview: FilePreview | null = null;
  let previewLimit = 50;
  let previewTable: string | null = null;
  let errorMsg: string | null = null;

  async function loadDomains(refresh = false) {
    try {
      const res: DomainsResponse = await listDataDomains(fetch, refresh);
      domains = res.domains;
      skipped = res.skipped;
    } catch (e: any) {
      errorMsg = "Failed to load domains: " + e.message;
    }
  }
  async function loadFiles() {
    try {
      files = await listDataFiles(fetch);
    } catch (e: any) {
      errorMsg = "Failed to load files: " + e.message;
    }
  }
  async function loadSample() {
    if (!selectedDomain) return;
    loadingSample = true;
    try {
      domainSample = await getDomainSample(fetch, selectedDomain, sampleLimit);
    } catch (e: any) {
      errorMsg = "Sample error: " + e.message;
    } finally {
      loadingSample = false;
    }
  }
  function selectDomain(d: string) {
    selectedDomain = d;
    domainSample = null;
    loadSample();
  }

  async function openFile(f: DataFileEntry) {
    selectedFile = f;
    filePreview = null;
    previewTable = null;
    try {
      filePreview = await previewDataFile(fetch, f.path, previewLimit);
    } catch (e: any) {
      errorMsg = "Preview error: " + e.message;
    }
  }
  async function refreshPreview() {
    if (!selectedFile) return;
    filePreview = null;
    try {
      filePreview = await previewDataFile(
        fetch,
        selectedFile.path,
        previewLimit,
        previewTable || undefined
      );
    } catch (e: any) {
      errorMsg = "Preview error: " + e.message;
    }
  }

  $: filteredFiles = files.filter(
    (f) =>
      !fileFilter ||
      f.kind.includes(fileFilter) ||
      f.path.toLowerCase().includes(fileFilter.toLowerCase())
  );

  onMount(() => {
    loadDomains();
    loadFiles();
  });
</script>

<h1>Data Browser</h1>
{#if errorMsg}<div class="error">{errorMsg}</div>{/if}

<div class="domains-layout">
  <header>
    <h3>Domains</h3>
    <button on:click={() => loadDomains(true)}>Refresh</button>
  </header>
  <table class="tbl small">
    <thead
      ><tr
        ><th>Domain</th><th>Type</th><th>Rows</th><th>Cols</th><th>Features</th
        ></tr
      ></thead
    >
    <tbody>
      {#each domains as d}
        <tr
          class:selected={selectedDomain === d.domain}
          on:click={() => selectDomain(d.domain)}
        >
          <td>{d.domain}</td><td>{d.type}</td><td>{d.rows}</td><td>{d.cols}</td
          ><td>{d.features.length}</td>
        </tr>
      {/each}
      {#if !domains.length}<tr
          ><td colspan="5" class="muted">(no domains)</td></tr
        >{/if}
    </tbody>
  </table>
  {#if skipped.length}
    <details class="skipped">
      <summary>Skipped ({skipped.length})</summary>
      <ul>
        {#each skipped as s}<li>{s.domain}: {s.reason}</li>{/each}
      </ul>
    </details>
  {/if}
</div>
<div class="domains-layout">
  <header>
    <h3>Domain Sample</h3>
    <div class="inline-controls">
      <label
        >Limit <input
          type="number"
          bind:value={sampleLimit}
          min="10"
          max="1000"
        /></label
      >
      <button on:click={loadSample} disabled={!selectedDomain || loadingSample}
        >{loadingSample ? "Loading..." : "Reload"}</button
      >
    </div>
  </header>
  {#if domainSample}
    <div class="sample-meta">
      {domainSample.domain} • {domainSample.rows.length} rows • {domainSample
        .columns.length} cols
    </div>
    <div class="table-wrap">
      <table class="tbl scroll">
        <thead
          ><tr
            >{#each domainSample.columns as c}<th>{c}</th>{/each}</tr
          ></thead
        >
        <tbody>
          {#each domainSample.rows as r}
            <tr
              >{#each domainSample.columns as c}<td>{r[c]}</td>{/each}</tr
            >
          {/each}
        </tbody>
      </table>
    </div>
  {:else if selectedDomain}
    <div class="muted">No sample loaded yet.</div>
  {:else}
    <div class="muted">Select a domain to view sample.</div>
  {/if}
</div>
<div class="domains-layout">
  <h2 style="margin-top:2rem;">Files</h2>
  <div class="domains-layout">
    <div class="file-toolbar">
      <label
        >Filter <input
          type="text"
          placeholder="kind or path"
          bind:value={fileFilter}
        /></label
      >
      <span class="count">{filteredFiles.length} files</span>
    </div>
    <div class="file-list">
      <table class="tbl small">
        <thead
          ><tr><th>Kind</th><th>Size</th><th>Modified</th><th>Path</th></tr
          ></thead
        >
        <tbody>
          {#each filteredFiles as f}
            <tr
              class:selected={selectedFile && selectedFile.path === f.path}
              on:click={() => openFile(f)}
            >
              <td>{f.kind}</td>
              <td>{(f.size / 1024).toFixed(1)}k</td>
              <td>{new Date(f.mtime * 1000).toLocaleDateString()}</td>
              <td class="path">{f.path}</td>
            </tr>
          {/each}
          {#if !filteredFiles.length}<tr
              ><td colspan="4" class="muted">(no files)</td></tr
            >{/if}
        </tbody>
      </table>
    </div>
  </div>
  <div class="domains-layout">
    <header><h3>Preview</h3></header>
    {#if filePreview}
      <div class="preview-meta">{filePreview.kind} • {filePreview.path}</div>
      {#if filePreview.text}
        <pre class="text-preview">{filePreview.text}</pre>
      {:else if filePreview.rows}
        {#if filePreview.text && filePreview.text.startsWith("tables:")}
          <div class="muted">{filePreview.text}</div>
        {/if}
        <div class="inline-controls">
          <label
            >Limit <input
              type="number"
              bind:value={previewLimit}
              min="10"
              max="1000"
            /></label
          >
          {#if filePreview.kind === "duckdb" || filePreview.kind === "sqlite"}
            <input
              type="text"
              placeholder="table (optional)"
              bind:value={previewTable}
            />
          {/if}
          <button on:click={refreshPreview}>Reload</button>
        </div>
        <div class="table-wrap">
          <table class="tbl scroll">
            <thead
              ><tr
                >{#each filePreview.columns as c}<th>{c}</th>{/each}</tr
              ></thead
            >
            <tbody>
              {#each filePreview.rows as r}
                <tr
                  >{#each filePreview.columns as c}<td>{r[c]}</td>{/each}</tr
                >
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <div class="muted">(empty)</div>
      {/if}
    {:else}
      <div class="muted">Select a file to preview.</div>
    {/if}
  </div>
</div>

<style>
  h1 {
    margin-bottom: 0.75rem;
  }
  .domains-layout {
    font-size: 1rem;
    background-color: #111;
    border: #1e293b solid 1px;
    border-radius: 0.5rem;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  button {
    background: #1e293b;
    border: 1px solid #334155;
    color: #e2e8f0;
    padding: 4px 10px;
    font-size: 0.7rem;
    border-radius: 4px;
    cursor: pointer;
  }
  button:hover {
    background: #0f172a;
  }
  table.tbl {
    width: 100%;
    border-collapse: collapse;
    font-size: 1rem;
  }
  table.tbl th,
  table.tbl td {
    border-bottom: 1px solid #222;
    padding: 2px 4px;
    text-align: left;
  }
  table.tbl tr.selected {
    background: #1e293b;
  }
  table.tbl tr:hover {
    background: #1b2534;
  }
  .tbl.small th,
  .tbl.small td {
    font-size: 1;
  }
  .muted {
    color: #666;
    font-size: 1;
  }
  .skipped {
    font-size: 1;
  }
  .table-wrap {
    overflow: auto;
    max-height: 300px;
    border: 1px solid #222;
  }
  .file-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
  }
  .file-list {
    max-height: 320px;
    overflow: auto;
  }
  .path {
    font-family: monospace;
    max-width: 320px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .text-preview {
    background: #0f172a;
    padding: 6px;
    max-height: 300px;
    overflow: auto;
    font-size: 1rem;
  }
  .inline-controls {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  input[type="text"],
  input[type="number"] {
    background: #111;
    border: 1px solid #333;
    color: #e2e8f0;
    padding: 2px 4px;
    font-size: 0.65rem;
    border-radius: 3px;
  }
  .error {
    background: #451a1a;
    border: 1px solid #7f1d1d;
    color: #fca5a5;
    padding: 6px 8px;
    font-size: 0.7rem;
    margin-bottom: 0.75rem;
  }
  .preview-meta,
  .sample-meta {
    font-size: 0.6rem;
    color: #94a3b8;
  }
</style>
