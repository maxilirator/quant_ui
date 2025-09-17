# Quant UI FastAPI Adapter (Read-Only)

This service is a thin **read-only** adapter that exposes strategy, feature, primitive,
artifact and panel slice data from an **external quant research engine** located at
`QUANT_CORE_ROOT` (e.g. `/dev/quant`). It deliberately **does not** implement strategy
training, backtests, job orchestration, order routing or DSL generation – those remain
in the upstream engine environment. All mutation endpoints from the early prototype
return `501 Not Implemented`.

## Getting started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The service exposes a curated subset of routes under the `/api` prefix. OpenAPI docs:
`http://127.0.0.1:8000/docs`.

## Exposed Endpoints (Summary)

| Route                           | Method | Purpose                                                           |
| ------------------------------- | ------ | ----------------------------------------------------------------- |
| /api/health                     | GET    | Liveness + version                                                |
| /api/strategies                 | GET    | List available strategies (external adapter or fallback sample)   |
| /api/strategies/{hash}          | GET    | Strategy detail                                                   |
| /api/strategies/{hash}/curve    | GET    | Equity curve                                                      |
| /api/strategies/{hash}/returns  | GET    | Derived daily returns (from equity)                               |
| /api/strategies/{hash}/analysis | GET    | Static expression analysis (features & primitives)                |
| /api/metrics/aggregate          | GET    | Sample aggregate metrics (placeholder)                            |
| /api/config/features            | GET    | Feature catalog (external or sample)                              |
| /api/config/primitives          | GET    | Primitive catalog (external or sample)                            |
| /api/panel/slice                | GET    | Narrow time-series slice (bars) with optional date/ticker filters |
| /api/artifacts/manifest         | GET    | Raw artifact manifest JSON                                        |
| /api/artifacts/models           | GET    | Filtered list (kind=model)                                        |
| /api/artifacts/reports          | GET    | Filtered list (kind=report)                                       |
| /api/artifacts/signals          | GET    | Filtered list (kind=signal)                                       |
| /api/artifacts/logs             | GET    | Filtered list (kind=log)                                          |
| /api/artifacts/datasets         | GET    | Filtered list (kind=dataset)                                      |
| /api/artifacts/strategies       | GET    | Filtered list (kind=strategy\*/see note)                          |

Disabled (return 501) routes: `/api/backtest`, `/api/jobs/*`, `/api/broker/*`.

> NOTE: The manifest currently stores `kind` by singularizing the directory name naïvely; `strategies` may appear as `strategie`. This will be normalized in a later patch.

### Two-System Architecture Reminder

This adapter **only reads** externally produced research artifacts. All generation of:

| Artifact Type                                      | Produced Here?            | Source (Expected)                  |
| -------------------------------------------------- | ------------------------- | ---------------------------------- |
| Strategy backtests / equity curves                 | ❌                        | quant core pipelines / runs DB     |
| DSL expression generation                          | ❌                        | quant core (AI / search modules)   |
| Model training (alpha, ML)                         | ❌                        | quant core training scripts        |
| Datasets (feature/label parquet)                   | ❌                        | quant core ingestion + build steps |
| Manifests (artifact inventory)                     | ❌                        | quant core build / CI job          |
| Visualization analytics (drawdowns, rolling stats) | ✅ (computed transiently) | Derived on-the-fly                 |

If a feature requires _producing_ or _mutating_ research state, implement it upstream in the quant core repo and expose only the resulting artifacts or a thin API surface here.

Never add heavy backtest loops, AI generation, or training logic to this adapter; that would violate the separation-of-concerns contract and risk performance / security regressions.

## Environment Variables

The service honours the following variables (defaults shown):

```text
QUANT_DB_PATH=./runs.sqlite
QUANT_DATA_ROOT=./data_curated
QUANT_RAW_ROOT=./data_raw
QUANT_API_KEY=                       # optional
BROKER_MODE=dummy
QUANT_CORE_ROOT=                     # optional path to external quant core (e.g. C:/dev/quant)
CORE_ROOT=                           # alternate unprefixed env name
```

If either `QUANT_CORE_ROOT` or `CORE_ROOT` is set, the service will prepend the resolved path to `sys.path` at startup so
you can import your research engine modules directly inside route handlers without vendoring or packaging yet. The
precedence order is:

1. `QUANT_CORE_ROOT`
2. `CORE_ROOT`
3. Any value provided via settings instantiation (not typical outside tests)

Example `.env` snippet on Windows PowerShell (escaping not required if no spaces):

```powershell
Set-Content -Path .env -Value @'
QUANT_CORE_ROOT=C:/dev/quant
QUANT_DATA_ROOT=./data_curated
QUANT_RAW_ROOT=./data_raw
QUANT_DB_PATH=./runs.sqlite
BROKER_MODE=dummy
'@
```

Or ad‑hoc for a single run (session only):

```powershell
$env:QUANT_CORE_ROOT='C:/dev/quant'; uvicorn app.main:app --reload
```

On Unix shells:

```bash
export QUANT_CORE_ROOT=/dev/quant
uvicorn app.main:app --reload
```

If the path does not exist, the app sets `app.state.quant_core_missing` for later diagnostics.

### Read-Only Security Guard

All non-GET methods (except OPTIONS/HEAD) are blocked by middleware. If `QUANT_API_KEY`
is set, artifact endpoints (`/api/artifacts/*`) require header:

```
X-API-Key: <value-of-QUANT_API_KEY>
```

### Artifact Manifest

Run the provided CLI to generate / refresh the manifest after upstream jobs:

```bash
python -m app.cli.build_manifest build --artifacts artifacts --git $(git rev-parse --short HEAD) --data-version <data_version>
```

The manifest (JSON) contains flattened entries with fields:

```jsonc
{
  "generated_at": "2025-09-15T21:18:33Z",
  "git_commit": "abc1234",
  "data_version": "20250915_fund_v2",
  "version": 1,
  "entries": [
    {
      "file": "models/model_20250915.json",
      "sha256": "...",
      "size": 1234,
      "created": "2025-09-15T21:37:00Z",
      "kind": "model"
    }
  ]
}
```

### Panel Slice Endpoint

`GET /api/panel/slice?start=YYYY-MM-DD&end=YYYY-MM-DD&tickers=A,B` returns a capped
row set (`MAX_ROWS=25000`) with optional stride downsampling indicator.

### Adapter Resolution Logic

On first request, the adapter attempts to import well-known external modules:
`quant_core.api`, `quant_core.results`, `quant_core.catalog`. If imports fail, sample
in-memory data is served. This allows the UI to function without the engine present.

---

## Migration From Prototype

If you previously used mutation endpoints for training/backtest, switch to invoking
those operations directly in the external engine environment and regenerating the
artifact manifest consumed here.

---

## Planned Enhancements

| Area          | Enhancement                                    |
| ------------- | ---------------------------------------------- |
| Manifest      | Normalize plural → singular kinds (strategies) |
| Artifacts     | ETag support + pagination for large lists      |
| Security      | Per-route key scoping (optional)               |
| Observability | Basic request metrics and cache headers        |

## Control API (Optional Local Orchestration)

A minimal "control" layer is available to trigger _whitelisted_ quant-core related
commands (export artifacts, etc.) directly from the existing FastAPI process **without**
introducing a second microservice. This remains optional and is primarily for local
operator convenience / a future UI control panel.

Key design constraints:

- Whitelist only (no arbitrary shell): registry in `app/control/registry.py`.
- Subprocess isolation: each task runs via `python -m <module>` to avoid leaking state.
- In-memory job ledger (non-persistent); safe for local dev.
- Read-only guard relaxed only for routes under `/api/control/*`.

### Endpoints

| Method | Route                             | Description                              |
| ------ | --------------------------------- | ---------------------------------------- |
| GET    | /api/control/tasks                | List available tasks & parameter schemas |
| POST   | /api/control/tasks/{task_id}/run  | Launch a task (returns job id)           |
| GET    | /api/control/jobs                 | List jobs                                |
| GET    | /api/control/jobs/{job_id}        | Job detail + status                      |
| GET    | /api/control/jobs/{job_id}/logs   | Full stdout/stderr (capped)              |
| POST   | /api/control/jobs/{job_id}/cancel | Attempt cancellation                     |

### Example: Export Artifacts (Synthetic)

```powershell
# List tasks
Invoke-RestMethod http://127.0.0.1:8000/api/control/tasks

# Run export (synthetic strategies)
$job = Invoke-RestMethod -Method POST \
  -Uri http://127.0.0.1:8000/api/control/tasks/export_artifacts/run \
  -Body (@{ params = @{ synthetic = $true; limit = 5; out_root = 'C:/dev/quant_generated' } } | ConvertTo-Json) \
  -ContentType 'application/json'

# Poll status
Invoke-RestMethod http://127.0.0.1:8000/api/control/jobs/$($job.id)

# Fetch logs
Invoke-RestMethod http://127.0.0.1:8000/api/control/jobs/$($job.id)/logs
```

### Adding a New Task

1. Edit `app/control/registry.py`.
2. Create a new `TaskDef` with a builder translating params to CLI args.
3. Restart the server; it appears in `/api/control/tasks`.

### Limitations & Future Hardening

| Aspect      | Current                 | Planned                               |
| ----------- | ----------------------- | ------------------------------------- |
| Auth        | None (local only)       | Header token / role gating            |
| Persistence | Volatile in-process     | SQLite / file-backed job index        |
| Streaming   | Polling only            | WebSocket incremental log stream      |
| Scheduling  | Manual trigger          | Cron-like / dependency graph          |
| Concurrency | Fixed small worker pool | Dynamic scaling / queue depth metrics |

Stay mindful of the two-system separation: _do not_ extend the control API into
heavy backtest loops or AI model training here; keep those responsibilities in the
core engine and expose only derived artifacts or coarse-grained triggers.
