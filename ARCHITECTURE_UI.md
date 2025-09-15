# Quant UI & API Architecture Roadmap

This document specifies the plan for building a SvelteKit-based user interface and a FastAPI backend service on top of the existing quant research/backtest engine.

---

## 1. High-Level Architecture

```
+------------------+        HTTPS / WS        +-----------------------+
|   SvelteKit UI   | <----------------------> |   FastAPI Service     |
|  (frontend app)  |                          |  (quant-ui backend)   |
+------------------+                          +-----------+-----------+
        | API client (fetch/WebSocket)                    |
        |                                                 |
        |                         +-----------------------+------------------+
  |                         |        quant-core (extracted)           |
  |                         |  - train_pipeline()                     |
  |                         |  - list_strategies(), get_strategy_detail() |
  |                         |  - dynamic feature catalog + DSL eval   |
  |                         |  - backtest & persistence wrappers      |
        |                         +-----------------------+------------------+
        |                                                 |
        |                                +----------------v----------------+
        |                                |       SQLite (runs, jobs)       |
        |                                +---------------------------------+
        |                                +---------------------------------+
        |                                | Data files (curated/raw, JSONL) |
        |                                +---------------------------------+
```

---

## 2. Core Goals

- Separate UI/service concerns from research engine.
- Provide stable programmatic API ("quant-core") instead of shelling out to CLI.
- Real-time job progress (WebSocket or SSE) for training/backtests.
- Visual exploration of strategies (tables, equity curves, distributions).
- Extensible path for broker integration (abstracted client layer).

---

## 3. API Endpoint Specification (v1)

| Method | Path                           | Purpose                         | Notes                        |
| ------ | ------------------------------ | ------------------------------- | ---------------------------- |
| GET    | /api/health                    | Liveness & version              | Git hash & core version      |
| GET    | /api/strategies                | Paginated list                  | params: limit, offset, order |
| GET    | /api/strategies/{hash}         | Metrics + expression            | Detail view                  |
| GET    | /api/strategies/{hash}/curve   | Equity curve                    | Downsampling param           |
| GET    | /api/strategies/{hash}/returns | Raw daily returns               | Chart overlay                |
| GET    | /api/metrics/aggregate         | Sharpe & drawdown distributions | Dashboard                    |
| POST   | /api/backtest                  | Ad-hoc expression backtest      | Optional persist             |
| POST   | /api/jobs/train                | Launch training job             | Body: job config             |
| GET    | /api/jobs                      | List jobs                       | Filter by status             |
| GET    | /api/jobs/{id}                 | Job status                      | Progress fields              |
| GET    | /api/jobs/{id}/log             | Tail job log                    | Optional pagination          |
| WS     | /api/jobs/{id}/stream          | Live job events                 | JSON progress/result         |
| GET    | /api/config/features           | Dynamic feature catalog         | For expression builder       |
| GET    | /api/config/primitives         | DSL primitive metadata          | Introspection                |
| GET    | /api/broker/positions          | Broker stub                     | Future                       |
| POST   | /api/broker/orders             | Place order (stub)              | Future                       |

---

## 4. Data Contracts

### 4.1 Strategy Summary

```json
{
  "expr_hash": "abc123",
  "expr": "clip(feat(\"c_sek\")/lag(feat(\"c_sek\"),1)-1)",
  "metrics": {
    "ann_return": 0.18,
    "ann_vol": 0.12,
    "ann_sharpe": 1.5,
    "max_dd": -0.08
  },
  "complexity_score": 14.2,
  "created_at": "2025-09-13T10:05:11Z"
}
```

### 4.2 Equity Curve

```json
{
  "expr_hash": "abc123",
  "base_currency": "SEK",
  "dates": ["2024-01-02", "2024-01-03"],
  "equity": [1.0, 1.002]
}
```

### 4.3 Job Create Request

```json
{
  "n": 50,
  "seed": 42,
  "workers": 4,
  "params": {
    "cap": 0.05,
    "max_lev": 1.0,
    "execution_lag": 1,
    "smooth_ema": null,
    "limit_score": 25.0
  }
}
```

### 4.4 Job Status

```json
{
  "job_id": "job_20250913_abcdef",
  "type": "train",
  "status": "running",
  "progress": 0.42,
  "processed": 21,
  "total": 50,
  "started_at": "...",
  "finished_at": null,
  "message": "Backtesting",
  "latest_sharpe": 1.34
}
```

### 4.5 WebSocket Event

```json
{
  "type": "progress",
  "job_id": "job_20250913_abcdef",
  "step": "backtest",
  "processed": 12,
  "total": 50,
  "elapsed_s": 4.21,
  "rate": 2.85,
  "expr_hash": "8f0c...",
  "sharpe": 1.12,
  "timestamp": "2025-09-13T10:06:11.234Z"
}
```

---

## 5. Backend Layering

```
quant_core/
  api.py
  types.py
  adapters/ (persistence, progress, catalog, runners)
quant_service/
  api/ (routers: strategies, jobs, backtest, config, broker)
  job_runner.py
  ws.py
  models.py (pydantic DTOs)
```

Progress callback signature (implemented):

```python
def progress_callback(event: dict):
  # event['type'] in {'phase','result','summary'}
  ...
```

Emitted events (current core implementation):

| Type    | Keys Example                                     | Meaning                                 |
| ------- | ------------------------------------------------ | --------------------------------------- |
| phase   | {"type":"phase","phase":"generate","count":N}    | Stage transition + rough item count     |
| result  | {"type":"result","expr_hash":"abc","sharpe":0.9} | Per-expression backtest outcome         |
| summary | {"type":"summary","elapsed_s":12.3,"count":N}    | Final aggregation after all persistence |

These map 1:1 onto planned WebSocket messages under `/api/jobs/{id}/stream`.

---

## 6. Front-End (SvelteKit) Routes & Components

| Route              | Purpose                                   |
| ------------------ | ----------------------------------------- |
| /                  | Dashboard metrics & histogram             |
| /strategies        | Strategy table (sortable/filterable)      |
| /strategies/[hash] | Detail: equity curve, metrics, expression |
| /backtest          | Ad-hoc expression runner                  |
| /jobs              | Job list                                  |
| /jobs/[id]         | Live job progress (WS)                    |
| /catalog           | Feature & primitives browser              |
| /broker            | (Future) positions/orders                 |

Components:

- `StrategyTable.svelte`
- `StrategyMetricsCard.svelte`
- `EquityCurveChart.svelte`
- `HistogramSharpe.svelte`
- `JobProgressBar.svelte`
- `ExpressionEditor.svelte`
- `FeatureBrowser.svelte`
- `LogViewer.svelte`

Stores:

- `strategies.ts`, `jobs.ts`, `catalog.ts`, `backtest.ts`

---

## 7. Phased Delivery Plan

| Phase | Focus               | Exit Criteria                             |
| ----- | ------------------- | ----------------------------------------- |
| 0     | Extract core API    | (Done) `quant_core.train_pipeline` tested |
| 1     | FastAPI skeleton    | /health & dummy /strategies respond       |
| 2     | Real strategy list  | Data from DB displayed                    |
| 3     | Training jobs       | Create + track job status                 |
| 4     | WebSocket streaming | Live progress updates                     |
| 5     | Ad-hoc backtest     | Expression form returns metrics & curve   |
| 6     | Catalog/primitives  | Autocomplete data available               |
| 7     | Metrics dashboard   | Sharpe hist + aggregates visible          |
| 8     | Broker stub         | Dummy positions/orders round-trip         |
| 9     | Auth & rate limits  | API key or token gating                   |
| 10    | Packaging           | Docker compose full stack                 |

---

## 8. DB Schema Extensions

```sql
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  params_json TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  started_at TEXT,
  finished_at TEXT,
  progress REAL,
  processed INTEGER,
  total INTEGER,
  message TEXT,
  last_event_ts TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS strategy_snapshots (
  expr_hash TEXT PRIMARY KEY,
  expr TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  complexity_score REAL,
  complexity_json TEXT
);
```

---

## 9. Logging & Observability

Structured JSON line format:

```
{"ts":"2025-09-13T10:15:00Z","level":"INFO","job_id":"...","event":"job_start","type":"train"}
{"ts":"2025-09-13T10:15:02Z","level":"INFO","job_id":"...","event":"expr_evaluated","processed":10,"total":50}
{"ts":"2025-09-13T10:15:07Z","level":"INFO","job_id":"...","event":"backtest_result","expr_hash":"8f0c","sharpe":1.2}
```

Health endpoint: `/api/health` (status + version).
Optionally `/api/metrics` for Prometheus exporter later.

---

## 10. Broker Stub Plan

Interface:

```python
class BrokerClient:
    def positions(self) -> list[dict]: ...
    def place_order(self, symbol, side, qty, order_type='mkt'): ...
    def cancel_order(self, order_id): ...
```

`dummy` implementation stores in-memory state.

---

## 11. Security & Deployment

Initial: open (dev). Later:

- Header `X-API-Key` or JWT (short-lived).
- CORS restricted to configured origin.
- Rate limit training job creation (e.g., <= 3 running).
  Deployment:
- SQLite WAL mode (already used).
- Docker compose (backend + frontend + volume mount for DB & data).
- Potential Postgres migration if write contention grows.

Environment variables:

```
QUANT_DB_PATH=./runs.sqlite
QUANT_DATA_ROOT=./data_curated
QUANT_RAW_ROOT=./data_raw
QUANT_API_KEY=devkey (optional)
BROKER_MODE=dummy
```

---

## 12. Risk & Mitigation

| Risk                            | Mitigation                                |
| ------------------------------- | ----------------------------------------- |
| DB lock contention              | Parent-only persistence; WAL mode         |
| Large equity payloads           | Downsample server-side (e.g., 500 points) |
| CPU spikes on big jobs          | Enforce cap on N expressions per job      |
| Unbounded job queue             | Add max concurrent + queue length guard   |
| Expression complexity explosion | Complexity score threshold server-side    |

---

## 13. Immediate Action Items

1. (Done) Add `quant_core/api.py` with `train_pipeline`, `list_strategies`, `get_strategy_detail`.
2. (Done) Progress callback plumbing returning phase/result/summary events.
3. Implement schema extension function for jobs table.
4. Draft FastAPI service stub (health + list strategies placeholder).
5. Initialize SvelteKit project with `/strategies` page.

---

## 14. Appendix: Minimal API Skeleton (Illustrative)

```python
# quant_core/api.py
from dataclasses import dataclass
from typing import Callable, List
from ..ai.dsl_gen import generate_expressions
from ..ai.batch_eval import batch_prepare
from ..ai.parallel_backtest import BacktestTask, run_parallel
from ..dsl.core import set_dynamic_catalog
from ..ai.feature_catalog import build_feature_catalog
from ..ai.persist import persist_backtest_result

@dataclass
class BacktestResult:
    expr: str
    expr_hash: str
    sharpe: float | None
    summary: dict

def train_pipeline(df, costs_df, n, params, workers=1, progress: Callable | None = None) -> List[BacktestResult]:
    catalog = build_feature_catalog(df, domain_lags=params.get('domain_lags', {}), ignore=params.get('ignore', []))
    set_dynamic_catalog(catalog)
    exprs = generate_expressions(n, seed=params.get('seed'), max_depth=params.get('max_depth', 4),
                                 allowed_terminals=[m.name for m in catalog])
    batch_meta = batch_prepare([e[0] for e in exprs], df)
    # Build tasks (omitted for brevity) -> run_parallel(...)
    # Persist results & invoke progress callback per task
    return []
```

---

## 15. Versioning Strategy

- Semantic version the new `quant-core` once API stabilizes (`0.1.0` start).
- UI pins `quant-core>=0.1.0,<0.2.0`.
- Breaking changes require minor version bump.

---

This file serves as the authoritative roadmap for the UI & API integration effort.
