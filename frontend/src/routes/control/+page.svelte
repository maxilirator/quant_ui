<script lang="ts">
  import { onMount } from "svelte";
  import {
    runControlTask,
    getControlJob,
    getControlJobLogs,
    cancelControlJob,
    listControlJobs,
    listRunsDB,
    listSignalFiles,
    listReturnFiles,
    listStrategyConfigs,
    fetchConfigFile,
    listModes,
    listMetrics,
    getControlMeta,
    listGenericConfigs,
  } from "$lib/api/client";
  import type {
    ControlTask,
    ControlJob,
    ControlJobLogs,
    ControlFileEntry,
  } from "$lib/api/types";
  export let data: {
    tasks: ControlTask[];
    jobs: ControlJob[];
    csvs: { path: string; size: number; mtime: number }[];
    fetchErrors: string | null;
  };

  let tasks: ControlTask[] = data.tasks;
  let jobs: ControlJob[] = data.jobs;
  let selectedTask: ControlTask | null = null;
  let params: Record<string, any> = {};
  let activeJob: ControlJob | null = null;
  let activeLogs: ControlJobLogs | null = null;
  let polling = false;
  let errorMsg: string | null = data.fetchErrors;
  // Discovery lists
  let runsDB: ControlFileEntry[] = [];
  let signalFiles: ControlFileEntry[] = [];
  let returnFiles: ControlFileEntry[] = [];
  let strategyCfgs: ControlFileEntry[] = [];
  let genericConfigs: ControlFileEntry[] = [];
  // Selected discovery values
  let selRunsDB: string | null = null;
  let selSignal: string | null = null;
  let selSignalDaily: string | null = null; // separate selection for daily_pipeline signal
  let selReturns: string | null = null;
  let selStrategiesCfg: string | null = null;
  let selWalkForward: string | null = null;
  let strategyCfgPreview: string | null = null;
  let previewLoading = false;
  let modesAvailable: string[] = [];
  let defaultMode: string | null = null;
  let metricInfos: { key: string; label: string; description: string }[] = [];
  let controlMeta: any = null;
  // raw data csvs for export_artifacts data param (reuse returnFiles filtered or separate fetch?) we reuse provided csvs list via data.csvs prop
  let rawDataFiles = data.csvs || [];
  // For curator tasks CSV selection
  let selBorsdata: string | null = null;
  let selEurSek: string | null = null;
  let selUniverse: string | null = null;
  // selections
  let selectedModes: Set<string> = new Set();
  let primaryOptions = ["sharpe", "cagr", "max_dd", "ann_vol", "ann_return"];
  let secondaryOptions = ["cagr", "sharpe", "max_dd", "ann_vol", "ann_return"];

  async function loadDiscovery() {
    try {
      runsDB = await listRunsDB(fetch);
    } catch {}
    try {
      signalFiles = await listSignalFiles(fetch);
    } catch {}
    try {
      returnFiles = await listReturnFiles(fetch);
    } catch {}
    try {
      strategyCfgs = await listStrategyConfigs(fetch);
    } catch {}
    try {
      genericConfigs = await listGenericConfigs(fetch);
    } catch {}
  }

  onMount(async () => {
    loadDiscovery();
    try {
      const m = await listModes(fetch);
      modesAvailable = m.modes;
      defaultMode = m.default;
    } catch {}
    try {
      metricInfos = await listMetrics(fetch);
    } catch {}
    try {
      controlMeta = await getControlMeta(fetch);
    } catch {}
  });

  function applyDefaultsForTask() {
    if (!selectedTask) return;
    if (selectedTask.id === "backtest_batch") {
      if (!params["out"]) params["out"] = "configs/strategies_sweep.json";
      if (!params["name_prefix"])
        params["name_prefix"] =
          "sweep_" + new Date().toISOString().slice(0, 10);
      if (modesAvailable.length && selectedModes.size === 0) {
        selectedModes.add(defaultMode || modesAvailable[0]);
        params["modes"] = Array.from(selectedModes);
      }
      if (!params["data_version"]) {
        // dynamic version string like vYYYYMMDD
        params["data_version"] =
          "v" + new Date().toISOString().slice(0, 10).replace(/-/g, "");
      }
    }
    if (selectedTask.id === "build_manifest") {
      if (controlMeta?.artifacts_root && !params["artifacts"])
        params["artifacts"] = controlMeta.artifacts_root;
      if (controlMeta?.git_commit && !params["git"])
        params["git"] = controlMeta.git_commit;
      if (!params["strategies_out"])
        params["strategies_out"] = "configs/strategies_sweep.json";
      // If strategies_out already present in strategyCfgs listing and no signal chosen, auto enable skip_sweep
      if (
        strategyCfgs.length &&
        strategyCfgs.find((s) => s.path === params["strategies_out"]) &&
        !params["signal"] &&
        params["skip_sweep"] === undefined
      ) {
        params["skip_sweep"] = true;
      }
      if (controlMeta?.data_version && !params["data_version"])
        params["data_version"] = controlMeta.data_version;
    }
    if (selectedTask.id === "daily_pipeline") {
      if ("ui_backend" in params) delete params["ui_backend"];
      if (controlMeta?.quant_core_root && !params["runs_db"])
        params["runs_db"] = controlMeta.quant_core_root + "/runs.sqlite";
      // default returns suggestion if none selected
      if (!params["returns"]) params["returns"] = guessDefaultReturns();
    }
    if (selectedTask.id === "export_artifacts") {
      if (controlMeta?.artifacts_root && !params["out_root"])
        params["out_root"] = controlMeta.artifacts_root + "/ui_export";
    }
    if (selectedTask.id === "select_strategies") {
      if (!params["returns"]) params["returns"] = guessDefaultReturns();
    }
  }

  function guessDefaultReturns(): string {
    if (returnFiles.length) {
      return returnFiles[0].path;
    }
    if (controlMeta?.quant_core_root) {
      return (
        controlMeta.quant_core_root + "/data_curated/panels_returns.parquet"
      );
    }
    return "data_curated/panels_returns.parquet";
  }

  function toggleMode(m: string) {
    if (selectedModes.has(m)) selectedModes.delete(m);
    else selectedModes.add(m);
    params["modes"] = Array.from(selectedModes);
  }

  function selectTask(t: ControlTask) {
    selectedTask = t;
    params = {};
    strategyCfgPreview = null;
    selRunsDB = selSignal = selReturns = selStrategiesCfg = null;
    selectedModes.clear();
    for (const p of t.params) {
      if (p.default !== undefined) params[p.name] = p.default;
    }
    applyDefaultsForTask();
  }

  async function previewConfig(path: string) {
    if (!path) {
      strategyCfgPreview = null;
      return;
    }
    previewLoading = true;
    try {
      const res = await fetchConfigFile(fetch, path);
      strategyCfgPreview = res.content;
    } catch (e: any) {
      strategyCfgPreview = "Failed to load config: " + e.message;
    } finally {
      previewLoading = false;
    }
  }

  async function launch() {
    if (!selectedTask) return;
    errorMsg = null;
    try {
      const job = await runControlTask(fetch, selectedTask.id, params);
      jobs = [job, ...jobs];
      activeJob = job;
      startPolling(job.id);
    } catch (e: any) {
      errorMsg = "Launch failed: " + e.message;
    }
  }

  async function refreshJobs() {
    try {
      jobs = await listControlJobs(fetch);
    } catch {}
  }

  function startPolling(jobId: string) {
    if (polling) return;
    polling = true;
    const poll = async () => {
      try {
        const j = await getControlJob(fetch, jobId);
        activeJob = j;
        const terminal = ["succeeded", "failed", "cancelled"].includes(
          j.status
        );
        activeLogs = await getControlJobLogs(fetch, jobId);
        if (terminal) {
          polling = false;
          refreshJobs();
          return;
        }
      } catch {
        polling = false;
        return;
      }
      if (polling) setTimeout(poll, 1500);
    };
    poll();
  }

  async function cancel(job: ControlJob) {
    try {
      const j = await cancelControlJob(fetch, job.id);
      activeJob = j;
    } catch (e: any) {
      errorMsg = "Cancel failed: " + e.message;
    }
  }
  function formatTs(ts?: number | null) {
    if (!ts) return "-";
    return new Date(ts * 1000).toLocaleTimeString();
  }
</script>

<h1>Control Panel</h1>
{#if errorMsg}<div class="error">{errorMsg}</div>{/if}
<div class="grid">
  <div>
    <h3>Tasks</h3>
    <div class="task-list">
      {#each tasks as t}
        <div
          class="task-item {selectedTask && selectedTask.id === t.id
            ? 'active'
            : ''}"
          on:click={() => selectTask(t)}
        >
          <div><strong>{t.id}</strong></div>
          <div class="desc">{t.summary}</div>
        </div>
      {/each}
    </div>
  </div>
  <div>
    <h3>Run Task</h3>
    {#if selectedTask}
      <div class="params">
        {#each selectedTask.params as p}
          {#if selectedTask.id === "build_curated_all" && p.name === "borsdata_csv"}
            <label class="field"
              ><span>{p.name}<small> Börsdata price/funda CSV</small></span>
              <select
                bind:value={selBorsdata}
                on:change={() => {
                  if (selBorsdata) params[p.name] = selBorsdata;
                }}
              >
                <option value="">(manual)</option>
                {#each rawDataFiles as f}<option value={f.path}>{f.path}</option
                  >{/each}
              </select>
              <input
                class="inline"
                type="text"
                placeholder="/path/to/stock_history.csv"
                bind:value={params[p.name]}
              />
            </label>
          {:else if selectedTask.id === "build_curated_all" && p.name === "eursek_csv"}
            <label class="field"
              ><span>{p.name}<small> EURSEK FX CSV</small></span>
              <select
                bind:value={selEurSek}
                on:change={() => {
                  if (selEurSek) params[p.name] = selEurSek;
                }}
              >
                <option value="">(manual)</option>
                {#each rawDataFiles as f}<option value={f.path}>{f.path}</option
                  >{/each}
              </select>
              <input
                class="inline"
                type="text"
                placeholder="/path/to/eursek.csv"
                bind:value={params[p.name]}
              />
            </label>
          {:else if selectedTask.id === "build_curated_all" && p.name === "universe_csv"}
            <label class="field"
              ><span>{p.name}<small> optional universe CSV</small></span>
              <select
                bind:value={selUniverse}
                on:change={() => {
                  if (selUniverse) params[p.name] = selUniverse;
                }}
              >
                <option value="">(manual)</option>
                {#each rawDataFiles as f}<option value={f.path}>{f.path}</option
                  >{/each}
              </select>
              <input
                class="inline"
                type="text"
                placeholder="/path/to/universe.csv"
                bind:value={params[p.name]}
              />
            </label>
          {:else if selectedTask.id === "build_curated_all" && p.name === "exogener"}
            <label class="field"
              ><span>{p.name}<small> space separated list</small></span>
              <input
                type="text"
                bind:value={params[p.name]}
                placeholder="DAX V2X Brent"
              />
            </label>
          {:else if selectedTask.id === "build_curated_all" && (p.name.startsWith("skip_") || p.name === "dry_run")}
            <label class="field"
              ><span>{p.name}<small> toggle</small></span>
              <input type="checkbox" bind:checked={params[p.name]} />
            </label>
          {:else if selectedTask.id === "build_curated_all" && (p.name === "calendar_start" || p.name === "calendar_end" || p.name === "data_version")}
            <label class="field"
              ><span
                >{p.name}<small>
                  {p.name === "data_version" ? "override" : ""}</small
                ></span
              >
              <input type="text" bind:value={params[p.name]} />
            </label>
          {:else if p.name === "runs_db"}
            <label class="field"
              ><span>{p.name}<small> runs sqlite</small></span>
              <select
                bind:value={selRunsDB}
                on:change={() => {
                  if (selRunsDB) {
                    params[p.name] = selRunsDB;
                  }
                }}
              >
                <option value=""> (manual) </option>
                {#each runsDB as f}<option value={f.path}>{f.name}</option
                  >{/each}
              </select>
              <input
                class="inline"
                type="text"
                placeholder={controlMeta?.quant_core_root
                  ? controlMeta.quant_core_root + "/runs.sqlite"
                  : "/path/to/runs.sqlite"}
                bind:value={params[p.name]}
              />
            </label>
          {:else if p.name === "strategies"}
            <label class="field"
              ><span>{p.name}<small> strategies config</small></span>
              <select
                bind:value={selStrategiesCfg}
                on:change={() => {
                  if (selStrategiesCfg) {
                    params[p.name] = selStrategiesCfg;
                    previewConfig(selStrategiesCfg);
                  }
                }}
              >
                <option value=""> (manual) </option>
                {#each strategyCfgs as f}<option value={f.path}>{f.name}</option
                  >{/each}
              </select>
              <input
                class="inline"
                type="text"
                placeholder="/path/to/strategies.json"
                bind:value={params[p.name]}
                on:change={() => previewConfig(params[p.name])}
              />
              {#if strategyCfgPreview}
                <details class="preview">
                  <summary>Preview</summary>
                  {#if previewLoading}<div class="preview-box">
                      Loading...
                    </div>{:else}<pre
                      class="preview-box">{strategyCfgPreview}</pre>{/if}
                </details>
              {/if}
            </label>
          {:else if p.name === "signal" && selectedTask.id === "backtest_batch"}
            <label class="field"
              ><span>{p.name}<small> signal parquet</small></span>
              <select
                bind:value={selSignal}
                on:change={() => {
                  if (selSignal) {
                    params[p.name] = selSignal;
                  }
                }}
              >
                <option value=""> (manual) </option>
                {#each signalFiles as f}<option value={f.path}>{f.name}</option
                  >{/each}
              </select>
              <input
                class="inline"
                type="text"
                placeholder="/path/to/signal.parquet"
                bind:value={params[p.name]}
              />
            </label>
          {:else if p.name === "signal" && selectedTask.id === "daily_pipeline"}
            <label class="field">
              <span
                >{p.name}<small>
                  signal parquet (leave empty + enable skip_sweep to reuse
                  existing strategies)</small
                ></span
              >
              <select
                bind:value={selSignalDaily}
                on:change={() => {
                  if (selSignalDaily) {
                    params[p.name] = selSignalDaily;
                    params["skip_sweep"] = false;
                  }
                }}
              >
                <option value=""> (manual) </option>
                {#each signalFiles as f}<option value={f.path}>{f.name}</option
                  >{/each}
              </select>
              <input
                class="inline"
                type="text"
                placeholder="/path/to/signal.parquet"
                bind:value={params[p.name]}
                on:change={() => {
                  if (params[p.name]) params["skip_sweep"] = false;
                }}
              />
            </label>
          {:else if p.name === "data" && selectedTask.id === "export_artifacts"}
            <label class="field"
              ><span>{p.name}<small> primary raw data CSV</small></span>
              <select
                on:change={(e: any) => {
                  const v = e.target.value;
                  if (v) params[p.name] = v;
                }}
              >
                <option value="">(manual)</option>
                {#each rawDataFiles as f}<option value={f.path}>{f.path}</option
                  >{/each}
              </select>
              <input
                class="inline"
                placeholder="/path/to/data.csv"
                type="text"
                bind:value={params[p.name]}
              />
            </label>
          {:else if selectedTask.id === "export_artifacts" && p.name === "fallback_data"}
            <label class="field"
              ><span
                >{p.name}<small>
                  secondary CSV (auto fallback only)</small
                ></span
              >
              <select
                on:change={(e: any) => {
                  const v = e.target.value;
                  if (v) params[p.name] = v;
                }}
              >
                <option value="">(manual)</option>
                {#each rawDataFiles as f}<option value={f.path}>{f.path}</option
                  >{/each}
              </select>
              <input
                class="inline"
                placeholder="/path/to/fallback.csv"
                type="text"
                bind:value={params[p.name]}
              />
            </label>
          {:else if selectedTask.id === "export_artifacts" && p.name === "auto_fallback"}
            <label class="field"
              ><span
                >{p.name}<small>
                  use data/fallback_data if runs empty</small
                ></span
              >
              <input type="checkbox" bind:checked={params[p.name]} />
            </label>
          {:else if selectedTask.id === "export_artifacts" && p.name === "mvp"}
            <label class="field"
              ><span
                >{p.name}<small> force MVP fallback (ignores runs)</small></span
              >
              <input
                type="checkbox"
                bind:checked={params[p.name]}
                on:change={() => {
                  if (params["mvp"]) {
                    params["synthetic"] = false;
                  }
                }}
              />
            </label>
          {:else if selectedTask.id === "export_artifacts" && p.name === "synthetic"}
            <label class="field"
              ><span>{p.name}<small> dev synthetic placeholders</small></span>
              <input
                type="checkbox"
                bind:checked={params[p.name]}
                on:change={() => {
                  if (params["synthetic"]) {
                    params["mvp"] = false;
                  }
                }}
              />
            </label>
          {:else if selectedTask.id === "export_artifacts" && p.name === "strict"}
            <label class="field"
              ><span>{p.name}<small> error if zero export</small></span>
              <input type="checkbox" bind:checked={params[p.name]} />
            </label>
          {:else if selectedTask.id === "select_strategies" && (p.name === "primary" || p.name === "secondary")}
            <label class="field"
              ><span>{p.name}<small> metric</small></span>
              <select bind:value={params[p.name]}>
                {(p.name === "primary" ? primaryOptions : secondaryOptions)
                  .map((opt) => opt)
                  .map((opt) => ({ opt }))}
                {#each p.name === "primary" ? primaryOptions : secondaryOptions as opt}
                  <option value={opt}>{opt}</option>
                {/each}
              </select>
            </label>
          {:else if selectedTask.id === "daily_pipeline" && p.name === "ui_backend"}
            <!-- hidden field intentionally omitted -->
          {:else if selectedTask.id === "daily_pipeline" && p.name === "skip_sweep"}
            <label class="field">
              <span
                >{p.name}<small>
                  skip generating new strategies (uses strategies_out)</small
                ></span
              >
              <input
                type="checkbox"
                bind:checked={params[p.name]}
                on:change={() => {
                  if (params[p.name]) {
                    delete params["signal"];
                    selSignalDaily = null;
                  }
                }}
              />
            </label>
          {:else if selectedTask.id === "build_manifest" && (p.name === "git" || p.name === "data_version")}
            <label class="field"
              ><span>{p.name}<small> suggestion</small></span>
              <input
                type="text"
                bind:value={params[p.name]}
                placeholder={p.name === "git"
                  ? controlMeta?.git_commit || "commit"
                  : controlMeta?.data_version || "data_version"}
              />
            </label>
          {:else if selectedTask.id === "select_strategies" && p.name === "strategies"}
            <label class="field"
              ><span>{p.name}<small> strategies json</small></span>
              <select
                on:change={(e: any) => {
                  const v = e.target.value;
                  if (v) {
                    params[p.name] = v;
                    previewConfig(v);
                  }
                }}
              >
                <option value=""> (manual) </option>
                {#each strategyCfgs as f}<option value={f.path}>{f.name}</option
                  >{/each}
              </select>
              <input
                class="inline"
                type="text"
                placeholder="/path/to/strategies.json"
                bind:value={params[p.name]}
                on:change={() => previewConfig(params[p.name])}
              />
              {#if strategyCfgPreview}
                <details class="preview">
                  <summary>Preview</summary>
                  {#if previewLoading}<div class="preview-box">
                      Loading...
                    </div>{:else}<pre
                      class="preview-box">{strategyCfgPreview}</pre>{/if}
                </details>
              {/if}
            </label>
          {:else if selectedTask.id === "select_strategies" && p.name === "returns"}
            <label class="field"
              ><span>{p.name}<small> returns panel</small></span>
              <select
                on:change={(e: any) => {
                  const v = e.target.value;
                  if (v) {
                    params[p.name] = v;
                  }
                }}
              >
                <option value=""> (manual) </option>
                {#each returnFiles as f}<option value={f.path}>{f.name}</option
                  >{/each}
              </select>
              <input
                class="inline"
                type="text"
                placeholder="/path/to/returns.parquet"
                bind:value={params[p.name]}
              />
            </label>
          {:else if selectedTask.id === "select_strategies" && p.name === "walk_forward"}
            <label class="field"
              ><span>{p.name}<small> config json</small></span>
              <select
                bind:value={selWalkForward}
                on:change={() => {
                  if (selWalkForward) {
                    params[p.name] = selWalkForward;
                    previewConfig(selWalkForward);
                  }
                }}
              >
                <option value=""> (manual) </option>
                {#each genericConfigs as f}<option value={f.path}
                    >{f.name}</option
                  >{/each}
              </select>
              <input
                class="inline"
                type="text"
                placeholder="/path/to/walk_forward.json"
                bind:value={params[p.name]}
                on:change={() => previewConfig(params[p.name])}
              />
              {#if strategyCfgPreview}
                <details class="preview">
                  <summary>Preview</summary>
                  {#if previewLoading}
                    <div class="preview-box">Loading...</div>
                  {:else}
                    <pre class="preview-box">{strategyCfgPreview}</pre>
                  {/if}
                </details>
              {/if}
            </label>
          {:else}
            <label class="field">
              <span
                >{p.name}{p.required ? "*" : ""}<small>{p.description}</small
                ></span
              >
              {#if p.type === "bool"}
                <input type="checkbox" bind:checked={params[p.name]} />
              {:else if p.type === "int"}
                <input type="number" bind:value={params[p.name]} />
              {:else}
                <input type="text" bind:value={params[p.name]} />
              {/if}
            </label>
          {/if}
        {/each}
        <button on:click={launch}>Run</button>
      </div>
    {:else}
      <p>Select a task to configure parameters.</p>
    {/if}

    <h3 style="margin-top:1.5rem;">Active Job</h3>
    {#if activeJob}
      <div class="job-info">
        <div><strong>ID:</strong> {activeJob.id}</div>
        <div>
          <strong>Status:</strong>
          <span class="status {activeJob.status}">{activeJob.status}</span>
        </div>
        <div><strong>PID:</strong> {activeJob.pid ?? "-"}</div>
        <div><strong>Exit:</strong> {activeJob.exit_code ?? "-"}</div>
        <div><strong>Started:</strong> {formatTs(activeJob.started_at)}</div>
        <div><strong>Finished:</strong> {formatTs(activeJob.finished_at)}</div>
        {#if activeJob.status === "running"}
          <button on:click={() => cancel(activeJob)}>Cancel</button>
        {/if}
        {#if activeLogs}
          <div class="logs-wrap">
            <h4>Logs</h4>
            <div class="logs">
              {#if activeLogs.stdout.length}
                {#each activeLogs.stdout.slice(-400) as line}
                  <div>{line}</div>
                {/each}
              {:else}
                <div class="muted">(no output yet)</div>
              {/if}
              {#if activeLogs.stderr.length}
                <div class="stderr-head">--- stderr ---</div>
                {#each activeLogs.stderr.slice(-200) as line}
                  <div class="err">{line}</div>
                {/each}
              {/if}
            </div>
          </div>
        {/if}
      </div>
    {:else}
      <p>No active job.</p>
    {/if}

    <h3 style="margin-top:1.5rem;">Recent Jobs</h3>
    <table class="jobs-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Task</th>
          <th>Status</th>
          <th>Exit</th>
          <th>Start</th>
          <th>End</th>
        </tr>
      </thead>
      <tbody>
        {#each jobs as j}
          <tr
            on:click={() => {
              activeJob = j;
              startPolling(j.id);
            }}
          >
            <td class="ellipsis">{j.id}</td>
            <td>{j.task_id}</td>
            <td>{j.status}</td>
            <td>{j.exit_code ?? "-"}</td>
            <td>{formatTs(j.started_at)}</td>
            <td>{formatTs(j.finished_at)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>

<style>
  .grid {
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 1rem;
  }
  .task-list {
    border: 1px solid #333;
    padding: 0.5rem;
    border-radius: 4px;
    max-height: 70vh;
    overflow: auto;
  }
  .task-item {
    padding: 0.4rem 0.5rem;
    cursor: pointer;
    border-radius: 3px;
  }
  .task-item:hover {
    background: #222;
  }
  .task-item.active {
    background: #444;
  }
  .desc {
    font-size: 0.7rem;
    color: #aaa;
  }
  .params {
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
  }
  .field {
    display: flex;
    flex-direction: column;
    font-size: 0.7rem;
    gap: 2px;
  }
  .field span {
    font-weight: 600;
    display: flex;
    gap: 4px;
    align-items: center;
  }
  .field small {
    font-weight: 400;
    color: #666;
  }
  .inline {
    margin-top: 2px;
  }
  select,
  input[type="text"],
  input[type="number"] {
    background: #111;
    border: 1px solid #333;
    color: #e2e8f0;
    padding: 4px 6px;
    border-radius: 4px;
    font-size: 0.75rem;
  }
  input[type="checkbox"] {
    transform: scale(1.1);
  }
  button {
    background: #1e293b;
    border: 1px solid #334155;
    color: #e2e8f0;
    padding: 6px 12px;
    font-size: 0.75rem;
    border-radius: 4px;
    cursor: pointer;
    align-self: flex-start;
  }
  button:hover {
    background: #0f172a;
  }
  .jobs-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.75rem;
  }
  .jobs-table th,
  .jobs-table td {
    padding: 4px 6px;
    border-bottom: 1px solid #333;
  }
  .ellipsis {
    max-width: 120px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .logs {
    background: #111;
    padding: 0.5rem;
    font-family: monospace;
    font-size: 12px;
    max-height: 240px;
    overflow: auto;
    border: 1px solid #333;
  }
  .stderr-head {
    margin-top: 0.5rem;
    color: #f87171;
    font-weight: 600;
  }
  .err {
    color: #f87171;
  }
  .muted {
    color: #555;
  }
  .preview {
    margin-top: 4px;
  }
  .preview-box {
    background: #0f172a;
    border: 1px solid #334155;
    padding: 8px;
    max-height: 320px;
    overflow: auto;
    font-size: 0.8rem;
  }
  .modes {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .mode-item {
    font-size: 0.65rem;
    background: #1e293b;
    padding: 2px 6px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .status.running {
    color: #38bdf8;
  }
  .status.failed {
    color: #f87171;
  }
  .status.succeeded {
    color: #4ade80;
  }
</style>
