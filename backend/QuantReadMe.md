# Quant Platform – Executive Summary

Core objective: a deterministic research & execution substrate enabling rapid, _safe_ strategy discovery.

Focus pillars:

1. **Data Integrity** – Atomic, idempotent ingestion → curated Parquet → audited DuckDB views.
2. **Expressive DSL** – Safe factor construction (time‑series + cross‑section primitives, constraints).
3. **Backtest Discipline** – Costs, leverage / turnover control, lockbox leakage prevention.
4. **AI Strategy Generation** – Guardrail‑bounded formula search with walk‑forward evaluation.

Key artifacts & living documents:

- Project plan: `PROJECT_PLAN.md` (phases, risks, metrics, gates)
- Operational checklist: `CHECKLIST.md` (Definition of Done status)
- DSL components: `src/dsl/`
- Backtest engine: `src/engine/`

### New Convenience DSL Primitives (Enhancement a)

Added to expand conditional & regime logic expressiveness:

- `ticker_mask(df, "TICKER")` – Feature returning 1.0 for the chosen ticker else 0.0 (per‑row float for arithmetic composition). Enables gating a sub‑signal to a single asset while mixing with macro / cross‑sectional conditions.
- `ret_n(series, n)` – Utility computing n‑period simple return `(series / lag(series,n)) - 1` with defensive coercion of `n` (robust to random generator passing a Series/array).
- `below_ma_pct(series, window, pct)` – Utility indicator (0/1 float) flagging when `series < (1 - pct) * moving_average(window)`; useful for pullback / discount or downside regime filters.
- `corr(a, b, window)` – Utility rolling correlation per ticker (or flat) with partial-window handling and defensive alignment; enables pair/spread & regime correlation logic.
- `spread_zscore(a, b, window)` – Utility rolling z-score of (a-b) spread per ticker for mean-reversion / convergence logic.
- `sector_ret(kind='sector')` – Broadcasts the average r1 return of each sector (or branch) to its constituents.
- `sector_vol(series, window, kind='sector')` – Rolling volatility of sector-average of a supplied series, broadcast back to members (requires series derived from DataFrame with sector metadata).

All return MultiIndex `(date,ticker)` aligned Series and carry metadata via `@dsl_meta`, so complexity scoring & evolutionary search can incorporate them immediately.

Status snapshot (see plan for details):

- Data: core tables + training_view scripts present, FX & costs partial
- DSL: parser/evaluator/constraints implemented (v1)
- Backtest: baseline PnL path operational
- AI generation: not started (guardrail design ready)

Next critical focus: finalize FX + QA JSON + formula complexity scoring + backtest smoke.

---

# Data – Definition of Done & Tests

## Goals (Data & Platform)

- Deterministic pipeline (same input ⇒ same output + data_version).
- “Fat but tidy” schema (raw + adjusted OHLCV, corp actions, FX, costs, calendar, universe).
- Survivorship-safe universe per date.
- Europe/Stockholm timezone + correct trading calendar.
- Traceable adjustments (split/div), QA flags, idempotence, performance.

## DoD Artifacts (Data Phase)

- Parquet: asset_master, universe_membership, corp_actions, bars_eod, fx_rates, cost_model_daily, trading_calendar
- DuckDB: `training_view` (joined bars + universe + fx + costs)
- `data_version.json` (sha256 of raw files + config)
- QA report JSON (counts, errors, warnings)
- Lockbox period frozen

## Tests (T00x–T09x – Current)

- **Schema**: T001_schema_match, T002_nullable_rules, T003_primary_keys
- **Calendar**: T010_timezone_eu_se, T011_trading_days, T012_close_consistency
- **Corp Actions / Adjustments**: T020_adjust_factors_monotonic, T021_raw_vs_adjusted, T022_dividend_gap
- **Universe**: T030_membership_on_date, T031_index_weight_sum, T032_new_delisted_transitions
- **Data Quality**: T040_missing_days, T041_duplicates, T042_outliers, T043_volume_zero_rule
- **FX**: T050_fx_alignment, T051_report_ccy_calc
- **Costs**: T060_cost_join, T061_spread_bounds
- **Idempotence**: T070_idempotent_run, T071_config_hash_effect
- **Performance**: T080_duckdb_query_time, T081_memory_ceiling
- **Lockbox**: T090_lockbox_readonly, T091_train_leak_check

## Acceptance Criteria (Data Phase Summary)

- All tests PASS.
- `training_view` query (one year OMXS30) < 1s local.
- QA report produced and `lockbox_protected: true`.

---

## Architecture (Layering)

1. **Ingestion**: Scripts normalize raw sources (Börsdata, FX, exogenous) → `data_curated/` with explicit schema & partitions.
2. **Curated Store**: Parquet tables (fat but structured) + `data_version` + QA flags.
3. **Query / DuckDB**: `training_view` materializes joins + costs + FX + universe.
4. **DSL Layer**: FeatureRegistry primitives + UTILS (ts/cs ops) + parser/evaluator.
5. **Backtest Engine**: Consumes DSL signal → weighting → constraints (beta/lev/turnover) → cost model.
6. **AI Strategy Gen**: Prompt + policy → expression graphs → syntactic & semantic validation → WF-CV.
7. **Validation & Guardrails**: Tests, leakage checks, lockbox, pre‑trade constraints.

## DSL & Strategy Generation

Components:

- **Parser/AST**: Pratt parser, nodes for literals, unary/binary operators, functions, ifelse.
- **Evaluator**: Converts expressions to pandas Series (MultiIndex date,ticker) in context.
- **FeatureRegistry**: Base functions (r1, lags, ma, rsi, atr, gap, spread, exogenous, fx, cs_rank/zscore, winsor, lag, zscore).
- **Constraints**: Beta neutralization, leverage scaling, cap, turnover, market close guard.
- **CV**: Purged walk‑forward + embargo (Lopez de Prado) + `kfold_summary`.

Planned extensions:

- Operator families: `rolling_corr`, `decay`, `regime_detect`, `sector_neutral`, `outlier_score`.
- Data source plugin (`datasources.py`) – dynamic discovery for AI.
- Formula complexity metric (depth, function count, cs/ts ratio) → policy control.
- Formula cache / memoization for repeated evaluation.

## AI Guardrails

- **Syntax**: Parser rejects invalid tokens, whitespace bug fixed (no space in OP class).
- **Semantics**: Type enforcement (Series vs scalar) + MultiIndex(date,ticker) validation.
- **Risk**: Automatic beta & leverage checks post-signal + turnover before/after scaling.
- **Leakage**: Directional lag discipline, no forward aggregates, purged WF + embargo.
- **Complexity**: Max depth, max cross‑section ops per expression, blocked combos.
- **Validation Pipeline**: (1) parse (2) sample eval (3) sanity metrics (nan, bounds) (4) WF-CV Sharpe/Drawdown (5) constraints PASS.

## Data Pipeline Details

- **Partitions**: bars (ticker/year), calendar (year), universe (year), costs (year), fx (ccy_pair), fundamentals (ticker).
- **Atomic Writes**: Temp file + rename, idempotent.
- **Versioning**: `data_version.json` = hash(raw files + config) → reproducibility.
- **Lockbox**: Read‑only historical window; tests enforce no write & no leakage.
- **QA**: JSON report (counts, nulls, outliers, coverage) linked to DoD.

### Strict Data Contract (Single Source of Truth)

The curated layer enforces a **single, zero‑tolerance file & partition contract**. Any deviation triggers an immediate `RegistryError`; no silent fallbacks or auto‑healing inside the loader. Historical one‑off migration is handled **only** by the `normalize` CLI.

Core rules:

1. Partition Naming
   - Every entity or dimension MUST be expressed as `key=value` (Hive style).
   - Examples: `ticker=ERIC`, `year=2024`, `ccy_pair=EURSEK`, `series=DAX`.
   - Prohibited: plain subdirectories like `ERIC/`, `2024/`, `EURSEK/`, `DAX/` (except a transient state before running the normalization command in a migration branch – not allowed to merge).
2. Domain Layouts
   - `bars_eod/`: `ticker=SYM/year=YYYY/*.parquet` (two‑level). Year partition optional for very small test sets but recommended for scalability.
   - `fundamentals/`: `ticker=SYM/*.parquet` (single level).
   - `universe_membership/`: `year=YYYY/*.parquet` (the registry still _reads_ bare `YYYY` for backward compatibility, but CI should assert none remain – see guard test).
   - `fx_rates/`: `ccy_pair=PAIR/*.parquet`.
   - `exogener/`: `series=NAME/*.parquet`.
   - `cost_model_daily/`: `year=YYYY/*.parquet`.
3. Column Requirements (per parquet file aggregated at partition load stage)
   - Must contain at least one date‑like column in {`date`,`Date`,`timestamp`,`ts`,`period_end` (fundamentals)}.
   - At least one **numeric** data column after removing bookkeeping columns (`date`, `ticker`, domain key fields) or file is ignored.
4. Feature Names
   - All numeric columns get a domain prefix (`fundamentals_`, `fx_rates_`, `exogener_`, etc.) during registry load (except bars core columns: `px_close`, `volume`).
5. Failure Mode
   - Presence of any non‑`key=value` directory (other than explicitly whitelisted e.g. hidden/temp) under a strict domain (`fundamentals`, `fx_rates`, `exogener`, any generic domain) raises immediately with a remediation hint: run normalization.
6. Reference Domains
   - Directories containing parquet but lacking a recognizable (date + numeric) time series signature are classified as `reference` and _omitted_ from the combined wide panel; they still appear in diagnostics metadata.
7. No Legacy Toggle
   - The former `--allow-legacy` / `allow_legacy` flag & code path were removed; contract drift must be fixed at the file system layer, not accommodated in code.
8. Synthetic Data Fallbacks
   - Removed (e.g. FX constant synthesis). Tests and runtime expect real normalized partitions present. If absent, a clear failure is preferred over silent imputation.

Recommended CI Gate:

```bash
python -m src.cli.ai_data diagnose --curated data_curated --format json | python -m scripts.assert_strict_contract
```

Where the helper script ensures:

- No domain metadata of type `collection` (legacy concept) exists.
- No plain subdirectory names remain (regex `^[^=]+$`).
- Optionally: enumerates a whitelist of domain keys and asserts extra unexpected keys are not present.

Migration Workflow (one‑time):

1. Run `ai_data normalize --dry-run` – confirm planned renames.
2. Run `ai_data normalize` – apply.
3. Commit the diff (partition directories renamed).
4. Add / update guard test (see `tests/test_registry_strict_contract.py`).
5. Remove any temporary synthetic data handling (already completed in this repo).

### Curated Domain Archetypes (Auto‑Discovery, Strict Mode)

| Type         | Detection (Strict)                                       | Example Layout                                | Feature Naming                                |
| ------------ | -------------------------------------------------------- | --------------------------------------------- | --------------------------------------------- |
| bars         | `bars_eod/` special case; `ticker=SYM/year=YYYY`         | `bars_eod/ticker=ERIC/year=2024/part.parquet` | `px_close` (+ volume)                         |
| fundamentals | `fundamentals/` special case; `ticker=SYM`               | `fundamentals/ticker=ERIC/f.parquet`          | `fundamentals_` prefix + aligned to bar dates |
| generic      | Directory whose children are ONLY `key=value` partitions | `fx_rates/ccy_pair=EURSEK/part.parquet`       | `<domain>_` prefix per numeric column         |
| flat         | Parquet files directly under domain (no subdirs)         | `macro_index/macro.parquet`                   | `<domain>_` prefix                            |
| universe     | `universe_membership/year=YYYY` partitions               | `universe_membership/year=2024/part.parquet`  | `universe_membership_in_universe` indicator   |
| reference    | Parquet present but no (date + numeric) time series      | `nordnet_costs/*.parquet`                     | Not merged, metadata only                     |

Alignment behaviors:

- Fundamentals: per‑ticker as‑of backward fill + leading backfill for pre‑first‑report bar dates.
- Universe: aligned to bar date/ticker grid; absent ⇒ 0.
- Generic domains: outer merged; sparsity preserved (no implicit fill).

Guard Test (added): ensures a legacy plain directory (e.g. `fx_rates/EURSEK`) triggers `RegistryError`.

### CLI Utilities: Normalization & Universe Coverage

Two maintenance‑oriented subcommands are available under the `ai_data` CLI to keep curated data tidy and to quantify universe completeness.

1. `normalize` – Retrofits legacy directory layouts (plain subdirectory naming) into the canonical `key=value` partition style.
2. `universe` – Reports coverage statistics for `universe_membership` relative to the bar grid.

#### 1. Directory Normalization

Purpose: migrate historical layouts such as:

```
data_curated/
   fx_rates/
      EURSEK/part.parquet
   exogener/
      DAX/data.parquet
   universe_membership/
      2024/part.parquet
```

…into the standardized partitioned form:

```
fx_rates/ccy_pair=EURSEK/part.parquet
exogener/series=DAX/part.parquet
universe_membership/year=2024/part.parquet
```

Dry‑run (plan only – prints intended rename operations):

```powershell
python -m src.cli.ai_data normalize --dry-run
```

Apply changes (idempotent; already normalized paths are skipped):

```powershell
python -m src.cli.ai_data normalize
```

Sample dry‑run output (plain):

```
ACTION  DOMAIN               FROM                          → TO
PLAN    fx_rates             fx_rates/EURSEK                fx_rates/ccy_pair=EURSEK
PLAN    exogener             exogener/DAX                   exogener/series=DAX
PLAN    universe_membership  universe_membership/2024       universe_membership/year=2024
```

JSON output (add `--format json`):

```jsonc
[
  {
    "domain": "fx_rates",
    "from": "fx_rates/EURSEK",
    "to": "fx_rates/ccy_pair=EURSEK",
    "status": "plan"
  },
  {
    "domain": "exogener",
    "from": "exogener/DAX",
    "to": "exogener/series=DAX",
    "status": "plan"
  }
]
```

Post‑application, re‑running with `--dry-run` should yield an empty plan, confirming idempotence.

Normalization rules (current):

| Domain                | Legacy Pattern             | Normalized Pattern              | Key Field  |
| --------------------- | -------------------------- | ------------------------------- | ---------- |
| `fx_rates`            | `fx_rates/PAIR`            | `fx_rates/ccy_pair=PAIR`        | `ccy_pair` |
| `exogener`            | `exogener/SERIES`          | `exogener/series=SERIES`        | `series`   |
| `universe_membership` | `universe_membership/YYYY` | `universe_membership/year=YYYY` | `year`     |

Additional patterns can be added with minimal risk; the command only renames directories that exactly match a known legacy shape and leaves already normalized paths untouched.

#### 2. Universe Coverage Metrics

The `universe` subcommand quantifies how completely the `universe_membership` table covers the `(date,ticker)` rows present in `bars_eod`.

Run (plain text):

```powershell
python -m src.cli.ai_data universe
```

Or JSON (machine‑readable):

```powershell
python -m src.cli.ai_data universe --format json
```

Reported fields:

| Field               | Meaning                                                   |
| ------------------- | --------------------------------------------------------- |
| `bar_rows`          | Total `(date,ticker)` combinations in bars                |
| `universe_rows`     | Total rows in aligned universe membership (indicator = 1) |
| `coverage_ratio`    | `universe_rows / bar_rows` (∈ [0,1])                      |
| `dates`             | `{count, first, last}` date span summary                  |
| `unique_tickers`    | Distinct tickers seen in bars                             |
| `per_date_universe` | `{min, max, avg}` number of in‑universe tickers per date  |
| `first_date_size`   | Universe size on the first trading date                   |
| `last_date_size`    | Universe size on the last trading date                    |

Sample JSON output:

```jsonc
{
  "bar_rows": 15420,
  "universe_rows": 14980,
  "coverage_ratio": 0.9714,
  "dates": { "count": 260, "first": "2024-01-02", "last": "2024-12-30" },
  "unique_tickers": 62,
  "per_date_universe": { "min": 54, "max": 61, "avg": 57.6 },
  "first_date_size": 55,
  "last_date_size": 60
}
```

Interpretation guidance:

- Coverage < ~0.95 may indicate missing membership periods or late starts for some tickers.
- A shrinking `last_date_size` vs `max` could flag recent delistings or data gaps.
- `min` substantially below `max` warrants inspection (e.g. corporate action induced suspensions).

This metric set is intentionally compact so it can be embedded in CI or surfaced in dashboards; richer longitudinal analytics (e.g. churn rates) can build on these primitives.

Combine with normalization: run `normalize` first to ensure consistent partition naming, then `universe` for stable metrics across runs.

## Test Expansion (Upcoming)

- **DSL**: Fuzz random expressions (restricted operator set) + determinism check.
- **Backtest Smoke**: Minimal strategy (e.g. cs_rank(r1)) → stable Sharpe sign, no exceptions.
- **Performance**: Max eval time per formula (e.g. < 300ms representative batch).
- **Regression**: Snapshot of known formulas & their CV metrics.

## Roadmap (Phased)

| Phase       | Scope                                                         | Exit Criteria                 |
| ----------- | ------------------------------------------------------------- | ----------------------------- |
| 1 Core Data | All T00x–T09x green, stable `training_view`                   | QA report, lockbox frozen     |
| 2 DSL+BT    | DSL v1 stable, backtest with constraints, baseline strategies | Smoke passes + latency budget |
| 3 AI Gen    | Formula generator + guardrails + WF-CV + result logging       | 100+ candidates ranked        |
| 4 Opt/Prod  | Memoization, caching, distributed evaluation                  | < X s batch 100 formulas      |
| 5 Monitor   | Drift metrics, deviation vs test                              | Alerting defined              |

## Operational Budgets (Targets)

- `training_view` one year query: < 1s (local SSD).
- DSL evaluation simple formula: < 50–100 ms (later < 20 ms with caching).
- WF-CV 10 folds (with 5 test days) medium dataset: < 5s.

## Risk & Mitigation

- **Leakage**: Lag discipline & purging mandatory; test T091 + new DSL leak tests.
- **Repro**: Hashed config, deterministic writer → historical reproduction.
- **Overfitting**: Walk‑forward + embargo + holdout lockbox.
- **Performance**: Profiling + operator vectorization + potential numba/pyarrow acceleration.

---

## Project Overview – (Historical / Original Plan)

1. Architecture & Environment
   Stack: Python 3.11, DuckDB, Parquet, Pandas/PyArrow.
   Storage: data_raw/ (immutable), data_curated/ (harmonized Parquet).
   DB: local quant.duckdb + views (primarily training_view).
   Timezone: Europe/Stockholm (EOD).
   Versioning: each write gets data_version (e.g. YYYYMMDD or git_sha).
   Lockbox: at least one frozen period (e.g. 2023–2024) for final validation.

2. Data Model (Parquet tables & views)
   Core datasets (curated):
   trading_calendar/ — columns: date, is_open, holiday_name, year, data_version. Partition: year=YYYY.
   bars_eod/ — columns: date, ticker, o_raw, h_raw, l_raw, c_raw, v, adjust_factor_cum, qa_flags, year, data_version. Partition: ticker=SYM/year=YYYY.
   fundamentals/ — columns: insId, ticker, date, revenues, gross_income, EPS, total_equity, non_current_liabilities, current_liabilities, cash_flow_from_operating_activities, free_cash_flow, dividend, net_debt, intangible_assets, total_assets, data_version. Partition: ticker=SYM.
   universe_membership/ — columns: date, universe_name, ticker, year, data_version. Partition: year=YYYY.
   fx_rates/ — columns: date, ccy_pair, close, source, data_version. Partition: ccy_pair=EURSEK (etc.).
   cost_model_daily/ — columns: date, ticker, commission_bps, half_spread_bps, impact_kbps, borrow_fee_bps, year, data_version. Partition: year=YYYY. (nordnet cost structure not migrated yet if needed).
   nordnet_costs — cost tiers per order size (future normalization candidate).
   DuckDB Views:
   training_view (joins calendar + universe + bars + fx + costs, producing SEK prices & costs per date,ticker).

3. Existing scripts (filenames)
   Calendar: ingest_calendar_se.py
   Prices (EOD, Börsdata): ingest_borsdata_bars.py
   Fundamentals (Börsdata → split handling): convert_borsdata.py
   Universe from EOD availability: ingest_universe_from_eod.py
   FX (Riksbanken SWEA / CSV): riksbank_api.py, ingest_fx_riksdata.py
   Nordnet costs: ingest_nordnet_costs_json.py, normalize_nordnet_costs.py
   QA / DoD document: CHECKLIST.md
   Pytest data skeleton: tests/test_costs.py

4. Current status
   Done: trading_calendar, bars_eod, fundamentals, universe_membership (EOD based).
   In progress: fx_rates (EUR/SEK via SWEA API), cost_model_daily v1, training_view (integration).
   Not started: exogenous (DAX, V2X, Brent), backtest engine, DSL, AI generation, trading engine.
   Finish EUR/SEK ingestion (SWEA API) → update training_view with reasonable FX forward fill.
   Build cost_model_daily v1 across universe_membership (commission, half_spread, impact-k).
   Run training_view end-to-end and sanity queries (coverage, zeros, ranges).
   Add exogenous: DAX, V2X, Brent (separate Parquet + left join in view).
   Implement backtest engine (open→close) with cost model, vol scaling, beta hedge.
   Define DSL v0.1 (features / signal / sizing / hedge / constraints / costs).

5. Next steps (priority order)
   Add AI generation of DSL strategies + validation (WF-CV, DSR, SPA).
   Trading engine (sim first): order sim, fill logic, daily rebalance.

6. QA / Tests (must be green before next phase)
   Schema/dtypes OK, unique keys per table, no duplicates.
   Calendar: no rows on closed days.
   Adjustments (when CA present): c_raw \* adjust_factor_cum ≈ c.
   FX: coverage & forward fill within reasonable horizon.
   Costs: join coverage ≥95% of date,ticker in universe.
   Idempotence: same input ⇒ same data_version + byte identical Parquet.
   Performance: one year query in training_view < ~1s local (SSD).

7. Decision log (short)
   Universe v1 = EOD availability with warm-up / gap rules.
   Parquet partitioning: ticker/year for bars, year for daily tables, ccy_pair for FX.
   Costs v1 = static assumptions, upgrade later with broker data.
   FX source = Riksbanken SWEA (series SEKEURPMI).

8. “Start new chat” – short prompt (legacy)
   Project overview please. Use the “Quant Platform” template. Status & next steps now tracked via roadmap table above.

---

## Quick Start (Dev)

````bash
pip install -r requirements.txt
pytest -q  # verify base data + DSL
python -m src.cli.build_all  # (if script present) run ingestion end-to-end

### Trade Data Ingestion (New)

If you have a raw daily trade CSV with OHLCV + metadata (name, sector, branch, list), convert it into the curated layout:

```powershell
python -m src.data.import_trade_data --raw data_raw/train_data.csv --curated data_curated --data-version DEV1
````

Incremental append, QA metrics, and sector mapping example:

```powershell
python -m src.data.import_trade_data \
   --raw data_raw/train_data.csv \
   --curated data_curated \
   --data-version $(git rev-parse --short HEAD) \
   --incremental \
   --sector-map data_raw/sector_map.csv \
   --qa-json artifacts/qa_trade_ingest.json
```

Outputs:

- `bars_eod/ticker=SYM/year=YYYY/part.parquet` containing: `date, ticker, c_sek, (optional o_sek,h_sek,l_sek,v)`
- `asset_master/ticker=SYM/asset.parquet` containing static fields: `ticker, name, sector, branch, list, first_trade_date, last_trade_date, currency, data_version`

Notes:

- Single close column `c_sek` replaces prior `px_close` duplication; registry updated to accept `c_sek` natively (falls back to legacy `px_close` if present).
- Add new tickers by re-running; existing partitions are idempotently replaced at file level.

* Provide `--data-version` to propagate provenance; otherwise a stable hash is computed.

````

## Programmatic Core API (`quant_core`)

In addition to the CLI tools there is a stable, importable layer in `src/quant_core/` that exposes a high‑level pipeline for:

1. Dynamic feature catalog construction (turn curated DataFrame columns into `feat("col")` terminals)
2. Random expression generation (complexity‑ordered)
3. Batch evaluation (single shared context → complexity + timing metadata)
4. Parallel backtesting (fast path; no redundant recomputation in parent)
5. Persistence to SQLite (`runs`, `run_returns`)

### Minimal Example

```python
import pandas as pd
from src.quant_core import train_pipeline, TrainConfig, list_strategies, get_strategy_detail
from src.data.registry import get_registry

# Load curated dataset (wide merged frame)
reg = get_registry('data_curated', raw_root='data_raw')
df = reg.load_all()
costs_df = df  # (placeholder – supply dedicated cost model if available)

cfg = TrainConfig(
   n=25,
   seed=42,
   max_depth=4,
   cap=0.05,
   max_lev=1.0,
   execution_lag=1,
   limit_score=25.0,
   workers=4,
   domain_lags={'fundamentals': 2},  # enforce reporting delay
)

results = train_pipeline(df, costs_df, 'runs.sqlite', cfg,
                   progress=lambda ev: print(ev))

print('First Sharpe:', results[0].summary.get('ann_sharpe'))

top = list_strategies('runs.sqlite', limit=5)
print('Top hashes:', [r['expr_hash'] for r in top])

detail = get_strategy_detail('runs.sqlite', top[0]['expr_hash'])
print('Daily returns points:', len(detail['daily_returns']))
````

### Progress Events

`train_pipeline(... progress=callback)` emits dictionaries with:

| Event Type | Shape (keys)                                     | Description                            |
| ---------- | ------------------------------------------------ | -------------------------------------- |
| `phase`    | `{"type":"phase","phase":str,"count":int}`       | Stage boundaries (generate, backtest…) |
| `result`   | `{"type":"result","expr_hash":str,"sharpe":num}` | Per backtested expression summary      |
| `summary`  | `{"type":"summary","elapsed_s":num,"count":int}` | Final aggregate                        |

These map directly to planned WebSocket messages in the UI layer (see `ARCHITECTURE_UI.md`).

### Returned Dataclasses

`train_pipeline` returns a list of `BacktestResult`:

| Field              | Meaning                                |
| ------------------ | -------------------------------------- |
| `expr`             | Expression text                        |
| `expr_hash`        | Structural hash (dedupe key)           |
| `complexity_score` | Weighted structural complexity         |
| `complexity`       | Dict of raw complexity components      |
| `eval_s`           | Evaluation (signal generation) seconds |
| `summary`          | Backtest summary metrics               |
| `params`           | Backtest parameter dict                |
| `daily_net`        | Pandas Series of per‑day net returns   |
| `error`            | Error string (if any stage failed)     |

### Relationship to CLI

`python -m src.cli.ai_run` now delegates internally to `train_pipeline`, so CLI and programmatic results stay consistent.

### Planned Endpoint Mapping (FastAPI)

| Function                   | Future Endpoint (planned)      | Notes                               |
| -------------------------- | ------------------------------ | ----------------------------------- |
| `train_pipeline`           | `POST /api/jobs/train` (async) | Job wrapper + streaming progress    |
| `list_strategies`          | `GET /api/strategies`          | Pagination / ordering server-side   |
| `get_strategy_detail`      | `GET /api/strategies/{hash}`   | Curve & metrics, complexity detail  |
| (future) single expression | `POST /api/backtest`           | Ad‑hoc backtest (not persisted opt) |

See `ARCHITECTURE_UI.md` for the full roadmap.

### Evolutionary Search (Experimental)

An experimental evolutionary engine is available: `evolution_search`.

```python
from src.quant_core import evolution_search, EvolutionConfig
evaluated = evolution_search(df, costs_df, 'runs.sqlite', EvolutionConfig(
   population_size=20,
   generations=4,
   seed=123,
   workers=4,
))
best = max(evaluated, key=lambda c: (c.summary or {}).get('ann_sharpe', float('-inf')))
print('Best Sharpe:', best.summary.get('ann_sharpe'))
```

Heuristics (v0):

- Text-level subtree replacement & crossover (no AST surgery yet)
- Mutation operators: literal replacement, subtree regeneration (depth≤2), wrapper function (`cs_rank`, `lag`, `winsor`, `clip`)
- Selection: top `elite_frac` by Sharpe (fallback negative complexity)
- Persistence: every evaluated candidate stored in the same `runs` / `run_returns` tables

Limitations / Roadmap:
| Area | Current | Planned |
| ---- | ------- | ------- |
| Structural ops | Regex / string splice | True AST node crossover/mutation |
| Objectives | Single (Sharpe) | Multi-objective (Pareto) |
| Diversity | None | Novelty / distance penalties |
| Pruning | None | Complexity & correlation pruning per gen |
| Guidance | Random elitist GA | Model-guided proposals |

## Examples – DSL Formulas

```text
cs_rank(ts_z(feat('r1'), 20))
0.5 * cs_z(feat('r1')) + 0.5 * cs_z(lag(feat('r1'), 5))
ifelse(cs_z(feat('r1')) > 1.5, -cs_rank(feat('r1')), cs_rank(feat('r1')))
```

## Robustness Features (DSL / Engine Layer)

| Component         | Location                                | Purpose                                                          | Usage                                                                          |
| ----------------- | --------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| AST Optimizer     | `src/dsl/optimizer.py`                  | Constant folding & lag collapsing                                | Enabled by default; disable with `compile(text, optimize_ast=False)`           |
| Signal Validators | `src/dsl/validators.py`                 | NaN ratio, infs, constant, amplitude checks                      | `eval_text(expr, df, validate=True)` or `eval_text(..., want_validation=True)` |
| Repro Harness     | `src/dsl/repro.py`                      | Deterministic RNG substreams                                     | `set_global_seed(123); rng = get_rng('alpha')`                                 |
| Evaluation Cache  | `src/dsl/exec.py`, `src/dsl/hashing.py` | Avoid re-computing duplicate subexpressions (structural hashing) | `eval_text(expr, df, use_cache=True, want_cache=True)`                         |
| Backtest Report   | `src/engine/backtest.py`                | Run DSL expression → enriched performance & cost analytics       | `from src.engine.backtest import backtest; rpt = backtest(expr, tv, costs)`    |

Example (strict validation that raises on failure):

```python
from src.dsl.exec import eval_text
sig = eval_text('ma(5) - ma(20)', df, validate=True).signal
```

Inspect metrics without raising:

```python
res = eval_text('ma(5)-ma(20)', df, want_validation=True)
print(res.validation.ok, res.validation.failures, res.validation.metrics)
```

Deterministic RNG stream:

```python
from src.dsl.repro import set_global_seed, get_rng
set_global_seed(42)
rng = get_rng('search')
noise = rng.normal(size=10)
```

### Structured Evaluation API (Signals + Metrics)

The legacy `compile_and_eval` helper has been **removed**. A fully structured API now provides richer telemetry and clearer semantics.

Core entry points:

| Function                           | Purpose                                                     | Typical Use                                 |
| ---------------------------------- | ----------------------------------------------------------- | ------------------------------------------- |
| `compile(text, optimize_ast=True)` | Parse (and optionally optimize) DSL source to AST           | Reuse AST across datasets or repeated evals |
| `eval_expr(ast, df, ...)`          | Evaluate pre‑compiled AST; opt‑in metrics                   | Tight loops / pre-parsed batches            |
| `eval_text(text, df, ...)`         | Parse + evaluate in one step; returns `EvalResult`          | Simple one‑off evaluations                  |
| `eval_batch([asts], df, ...)`      | Evaluate multiple ASTs sharing one context; aggregate stats | Strategy candidate batches                  |

Result dataclasses (all frozen / immutable):

```python
from src.dsl.exec import EvalResult, CacheStats, TimingStats, BatchEvalResult
```

Fields:

- `EvalResult.signal`: pandas Series indexed by (date, ticker)
- `EvalResult.cache`: `CacheStats` or None
  - `hits`, `misses`, `entries`, `nodes`, `hit_ratio`, `time_per_node`
- `EvalResult.timing`: `TimingStats` or None (`parse_optimize_s`, `eval_s`, `total_s`)
- `EvalResult.validation`: `ValidationResult` (if requested)

Quick examples:

```python
from src.dsl.exec import eval_text

# Basic evaluation
res = eval_text("ma(5) - ma(20)", df)
sig = res.signal

# With cache + timing + validation record (non‑raising)
res = eval_text("(ma(5)+ma(5))*ma(5)", df, use_cache=True, want_cache=True, want_timing=True, want_validation=True)
print(res.cache.hit_ratio, res.timing.eval_s, res.validation.metrics.keys())

# Precompile + reuse
from src.dsl.exec import compile, eval_expr
ast = compile("cs_rank(ts_z(feat('r1'), 20))")
res = eval_expr(ast, df, use_cache=True, want_cache=True)

# Batch evaluation (shared context)
asts = [compile(t) for t in ["ma(5)", "ma(10)", "ma(5)+ma(10)"]]
batch = eval_batch(asts, df, use_cache=True, want_cache=True, want_timing=True)
print(batch.aggregate_cache.hit_ratio, batch.aggregate_timing.total_s)
signals = batch.signals()  # list of Series
```

#### Caching (Structural Hash Memoization)

Purpose: skip redundant computation of identical sub‑expressions within a single evaluation. Each AST node gets a deterministic structural hash (commutative for `+`/`*`).

Key points:

- Disabled unless `use_cache=True`.
- Scope: evaluator instance only (no cross‑formula persistence yet).
- Request stats via `want_cache=True`.
- `CacheStats.nodes` counts total visited nodes (useful for perf normalization: `time_per_node`).

Interpreting metrics:

- `hit_ratio = hits / (hits + misses)`; expect higher ratios on formulas with repeated motifs.
- `time_per_node = eval_s / nodes`; baseline micro-efficiency (watch regressions across commits).

When beneficial: repeated sub‑trees (AI‑generated expressions, explicit duplication). For simple expressions overhead is negligible; you can keep caching off if micro‑benchmarking primitive operators.

#### Validation

Two modes:

- `validate=True`: run validators and raise `EvalError` if any fail.
- `want_validation=True`: include `ValidationResult` in `EvalResult.validation` (no raise even if failing unless `validate=True`).

Example (non‑raising introspection):

```python
res = eval_text("ma(5)-ma(5)", df, want_validation=True)
print(res.validation.ok, res.validation.failures)
```

#### Migration Notes (from removed compile_and_eval)

Old call:

```python
# signal = compile_and_eval(expr, df, use_cache=True, return_cache_stats=True, return_timing=True)
```

New equivalent:

```python
res = eval_text(expr, df, use_cache=True, want_cache=True, want_timing=True)
signal = res.signal
cache_stats = res.cache
timing = res.timing
```

Validation replacement:

```python
# old: sig, vr = compile_and_eval_with_validation(expr, df)
res = eval_text(expr, df, want_validation=True)
sig, vr = res.signal, res.validation
```

If you previously relied on tuple return shapes, update code to access named fields; dataclasses are frozen to guarantee immutability for downstream tooling.

Planned future extension: optional cross‑expression global cache layer & common subexpression elimination across batches.

## Backtest Report (Signal → Weights → PnL Analytics)

The backtest engine now returns a structured `BacktestReport` instead of a bare Series when calling `backtest()`.

### Core Entry Point

```python
from src.engine.backtest import backtest
rpt = backtest(
   "ma(10) - ma(30)",
   training_view,
   costs,
   cap=0.05,
   max_lev=1.0,
   smooth_ema=0.2,
   execution_lag=1,
   use_cache=True,
   want_timing=True,
)
daily = rpt.to_frame()
print(daily.head())
print(rpt.summary())
```

### Fields

| Field             | Description                                                               |
| ----------------- | ------------------------------------------------------------------------- |
| `weights`         | Final weights (date,ticker) after cap & leverage (and optional smoothing) |
| `signal`          | Raw signal used to derive weights                                         |
| `gross_returns`   | Daily pre-cost returns Σ w\_{t-1} \* r_t                                  |
| `net_returns`     | Gross minus total costs                                                   |
| `cost_breakdown`  | Turnover, linear, impact, borrow, total costs                             |
| `risk`            | Gross leverage, net exposure, long/short gross (beta placeholder)         |
| `enforcement_log` | Constraint events (cap/leverage adjustments)                              |
| `params`          | Run parameters (+ optional timing)                                        |

### Costs & Turnover

- Turnover: Σ |Δw_t|.
- Linear: (commission_bps + half_spread_bps)/1e4 \* turnover.
- Impact: impact_kbps / 1e5 \* turnover.
- Borrow: short gross \* borrow_fee_bps / 1e4 / 252.

### Risk Series

- Gross leverage Σ |w_i|; Net leverage Σ w_i; Long/Short gross; beta (future).

### Execution Lag

`execution_lag=1` applies returns with lagged weights (t decision, t+1 realization). Set 0 for idealized same-bar evaluation.

### Enforcement Log Example

```python
rpt.enforcement_log
# [{'constraint': 'cap', 'cap': 0.05}, {'constraint': 'leverage', 'max_lev': 1.0}]
```

### Migration

| Old                                      | New                                                             |
| ---------------------------------------- | --------------------------------------------------------------- |
| `pnl_series = backtest(expr, df, costs)` | `rpt = backtest(expr, df, costs); pnl_series = rpt.net_returns` |
| No cost breakdown                        | `rpt.cost_breakdown.total / linear / impact / borrow`           |
| No leverage series                       | `rpt.risk.gross_lev` etc.                                       |

### Upcoming

- Walk-forward CV wrapper (collection of reports + aggregate stats)
- Persistence layer for run logging
- Complexity score integration for ranking

## Further Development

Increase data sources (fundamentals, alternative data), extend operators, integrate AI formula generator, caching & distributed evaluation, production rollout with monitoring.

---

## Contributing New DSL Primitives (Single Source of Truth)

All DSL-exposed functions (features and utilities) are defined once in `src/dsl/primitives.py` and decorated with `@dsl_meta`. This eliminates duplication across the registry, core utilities, and arity logic.

### 1. Decide: Feature vs Utility

| Type    | Signature Pattern                           | DSL Call Looks Like             | First Arg in Python | Typical Use                                          |
| ------- | ------------------------------------------- | ------------------------------- | ------------------- | ---------------------------------------------------- |
| Feature | `def foo(df: pd.DataFrame, ...) -> Series`  | `foo(...)` (implicit DataFrame) | DataFrame (`df`)    | Base data-derived series (prices, indicators)        |
| Utility | `def bar(series: pd.Series, ...) -> Series` | `bar(expr, ...)`                | Series              | Transforms another expression (lag, ranks, z-scores) |

Rule of thumb: If it pulls directly from columns or joins data → Feature. If it transforms a computed series → Utility.

### 2. Add the Function in `primitives.py`

Example (new rolling median feature):

```python
@dsl_meta(arity=(1,1), weight=1.2, category='feature')
def med(df: pd.DataFrame, win: int) -> pd.Series:
   """Rolling median of close: med(window)."""
   win = int(win)
   s = df.set_index(["date","ticker"])['c_sek']
   out = s.groupby(level='ticker').rolling(win, min_periods=max(2, win//2)).median().droplevel(0)
   out.name = f"med{win}"
   return out
```

For a utility (e.g., exponential decay):

```python
@dsl_meta(arity=(2,2), weight=1.6, category='utility')
def decay(s: pd.Series, half_life: int) -> pd.Series:
   """Exponential decay of series toward 0 with given half-life."""
   hl = int(half_life)
   alpha = np.log(2) / max(1, hl)
   return s.groupby(level='ticker').apply(lambda x: x.ewm(alpha=alpha, adjust=False).mean())
```

### 3. Set Metadata Correctly

`@dsl_meta(arity=(min,max), weight=...)` arguments:

- `arity`: DSL call argument counts (exclude implicit `df` for features). Use `(1,None)` only if truly variadic (currently only `feat`).
- `weight`: Intrinsic complexity weight (affects formula complexity scoring). Rough guide: 0.1 trivial, 0.5 reference, 1.0 baseline, 1.5–2.0 heavier constructs.
- `category`: `'feature'` or `'utility'` (drives auto-registration).
- Additional keyword args (e.g. `doc="..."`) become part of metadata and available for discovery tools.

### 4. Arity & Defaults – Gotchas

If you provide Python defaults (e.g. `win: int = 20`) but you want the DSL to _require_ that argument, you MUST still declare `arity=(1,1)`; the arity map prefers metadata, so that's fine. To avoid confusion we removed defaults for required windowed features (e.g. `ma`, `rsi`).

### 5. Feature Naming & Collisions

Names are case-insensitive in the parser. Avoid overlapping a feature and utility name unless intentionally providing both forms (e.g. registry wraps utilities with a df-first adapter). If you rename/remove a primitive, update any tests referencing it (see `tests/test_dsl_arity_map.py`).

### 6. How Registration Works Under the Hood

1. `primitives.py` is imported.
2. Each decorated function calls `register_meta()` internally.
3. `FeatureRegistry` auto-discovers feature functions via their attached `_dsl_meta` and registers them.
4. The dynamic arity map (`arity.py`) merges metadata + inferred signatures + minimal explicit overrides (`feat`, `ifelse`, legacy alias `winsorize`, and enforced `zscore`).

### 7. Complexity Scoring Impact

Your `weight` feeds into intrinsic function cost inside complexity metrics. Large-scoped operations (cross-sectional, rolling with large windows, external data like `exog`) should carry higher weights to bias the AI generator toward simpler expressions first.

### 8. Tests That Will Fail If Misconfigured

- `tests/test_dsl_arity_map.py` – missing or incorrect arity.
- Any evaluation test using your new function if it violates MultiIndex assumptions.
- Complexity tests if you introduce unexpected intrinsic cost patterns (rare).

Run locally after adding a primitive:

```bash
pytest tests/test_dsl_arity_map.py::test_expected_core_arity_entries -q
pytest -q  # full sweep
```

### 9. MultiIndex Requirement

All Series returned must have index `(date,ticker)`. If you aggregate and lose levels, reassign with the DataFrame's index or propagate existing Series index to preserve alignment.

### 10. When to Use `feat()` Inside Another Primitive

Prefer direct reuse of Python functions (call the other primitive) rather than invoking the DSL `feat()` indirection—this keeps evaluation fast and arity inference clean.

### 11. Introducing a Variadic Function

If you need variadic semantics, set `arity=(n,None)` and document ordering rules. Update `tests/test_dsl_arity_map.py` to whitelist your new variadic name.

### 12. Deprecating a Primitive

Mark it in the docstring (`[DEPRECATED]`), leave metadata intact for at least one cycle, optionally add a runtime warning, then remove after downstream cleanup.

---

In short: implement in `primitives.py` with `@dsl_meta`, choose correct category, keep return index consistent, run tests. The rest (registry wiring, parser allowed set, arity map, complexity weights) updates automatically.

---

## Complexity Metrics & Expression Logging

You can request structural complexity analysis and optional CSV logging for each evaluated DSL expression.

### Getting Complexity

```python
from src.dsl.exec import eval_text
res = eval_text("cs_z(ma(5)) + lag(ma(3),1)", df, clip=None,
                 want_complexity=True, want_cache=True, want_timing=True)
print(res.complexity.as_dict())  # detailed metrics
print(res.complexity.score())    # weighted scalar
```

Metrics (prefixed `cx_` in logs):

| Metric                | Description                                                |
| --------------------- | ---------------------------------------------------------- |
| nodes                 | Total AST nodes                                            |
| depth                 | Max nesting depth                                          |
| distinct_funcs        | Count of distinct function calls                           |
| nonlinear_ops         | `*`, `/`, `^` occurrences (penalize non-linear transforms) |
| cross_sectional_funcs | Calls beginning with `cs_`                                 |
| external_data_funcs   | External data access (`exog`, `fx`)                        |
| sum_windows           | Sum of detected window sizes (e.g. `ma(10)` -> 10)         |
| max_window            | Largest single window size                                 |
| constants             | Numeric + string literals                                  |
| branches              | `ifelse` occurrences                                       |
| intrinsic_func_cost   | Sum of primitive `weight` metadata values                  |

`ComplexityMetrics.score(weights=None)` lets you override weight mapping (merge over defaults) to tailor search pressure (e.g., heavier penalty on `sum_windows`).

### Batch Mode

`eval_batch(..., want_complexity=True)` provides per-result metrics plus an aggregate (sums; depth/max_window are max). Use this to cap overall complexity budgets for candidate sets.

### CSV Logging

Set environment variable `QUANT_DSL_LOG` to a writable file path. A header is created if the file is empty; each evaluation appends one row.

PowerShell example:

```powershell
$Env:QUANT_DSL_LOG = "C:\temp\dsl_evals.csv"
```

Request any combination of:

- `want_complexity=True` → `cx_*` columns + `cx_score`
- `want_cache=True` → cache hit/miss/nodes stats
- `want_timing=True` → parse / eval timings

Columns always include `expr` (original text if available). Logging is best‑effort—IO errors are suppressed to avoid impacting evaluation latency.

### Workflow for Model-Guided Generation

1. Generate candidate expressions (AI / genetic / random walk).
2. Evaluate with complexity, timing, cache stats, logging enabled.
3. Join logged rows with downstream backtest performance (net returns, Sharpe) to build a ranking model.
4. Adjust primitive `weight` metadata to sculpt intrinsic cost landscape and re-score historical expressions.

---

## AI Integration: Random Expression Generator (v0)

An initial AI-support layer provides a stochastic expression generator with complexity-aware ranking. This seeds future ML-guided or evolutionary search.

### Programmatic Usage

```python
from src.ai.dsl_gen import generate_expressions
exprs = generate_expressions(n=20, max_depth=4, seed=123)
for txt, metrics, score in exprs[:5]:
      print(score, txt)
```

Returns a list of `(expr_text, complexity_metrics_dict, complexity_score)` sorted by ascending complexity score (simpler first) to encourage breadth-first exploration.

### CLI

```bash
python -m src.cli.ai_generate --n 50 --max-depth 5 --seed 7 --output exprs.jsonl
```

Optional evaluation (adds timing/cache columns and enables CSV logging if `QUANT_DSL_LOG` set):

```bash
python -m src.cli.ai_generate --n 30 --evaluate --data data_raw/stock_history.csv --seed 42 --output exprs_eval.jsonl
```

Each JSONL record:

```jsonc
{
   "expr": "cs_z(ma(5)) + lag(ma(3),1)",
   "complexity_score": 12.3,
   "complexity": {"nodes": ..., "depth": ...},
   "eval": {"parse_s": 0.00007, "eval_s": 0.0051, "hits": 0, "misses": 0, "signal_len": 1500}
}
```

Filter by score during generation:

```bash
python -m src.cli.ai_generate --n 200 --limit-score 25 --output simple.jsonl
```

### Generation Heuristics (Current)

- Depth-limited recursive construction (default max depth 4).
- Weighted choice among terminals (features, literals), binary ops, ifelse, function calls.
- Window / lag argument heuristics choose from a small discrete set for consistency and reproducibility.
- Optional optimizer pass before complexity scoring (`--no-opt` disables).

### Roadmap for Smarter Generation

| Stage    | Upgrade                                                  | Benefit                           |
| -------- | -------------------------------------------------------- | --------------------------------- |
| v0 (now) | Random + complexity sort                                 | Baseline exploration              |
| v1       | Complexity + cached performance replay (ranking model)   | Guided sampling                   |
| v2       | Evolutionary (mutate / crossover) with dominance pruning | Diversity + performance trade-off |
| v3       | LLM-conditioned expansion via prompt templates           | Semantic priors                   |

---

## NEW: Supervised Cross-Sectional Alpha Modeling (AI MVP)

In addition to stochastic DSL expression discovery, a lightweight supervised learning path is now available. This lets you construct a feature → future return dataset directly from the curated wide panel and train a linear cross‑sectional model.

### Components

- Module: `src/ai/dataset.py` – feature & label assembly utilities.
- CLI: `python -m src.cli.ai_alpha` with subcommands `build`, `train`, `predict`.

### Dataset Construction

```
python -m src.cli.ai_alpha build --curated data_curated --horizon 1 \
   --feature-prefix fundamentals_ --feature-prefix fx_rates_ \
   --out-dir artifacts/alpha_ds
```

Outputs (in `out-dir`):

- `features.parquet` – MultiIndex (date,ticker) matrix of selected features
- `labels.parquet` – future next‑day return label (column `label`)
- `meta.json` – horizon & feature metadata summary

Feature selection filters:

1. Prefix whitelist (via repeated `--feature-prefix` flags).
2. NA ratio threshold (default 0.40 – configurable in code for now).
3. Optional domain lag application (hook present, pass `domain_lags` programmatically).

No forward leakage: unless `allow_future_leak=True` (internal flag), domain lags would shift features backward; current CLI build path uses raw features (future: add `--apply-domain-lags`).

### Training

```
python -m src.cli.ai_alpha train --dataset artifacts/alpha_ds --model artifacts/alpha_model.json
```

Trains a closed‑form ridge‑stabilized OLS (`linear_cs`) model. Artifact fields:

| Field            | Meaning                        |
| ---------------- | ------------------------------ |
| model_type       | `linear_cs`                    |
| features         | Ordered feature list           |
| coef / intercept | Learned parameters             |
| r2_in_sample     | In‑sample R² (diagnostic only) |
| horizon          | Label horizon (days)           |

### Prediction (Daily Cross-Section)

```
python -m src.cli.ai_alpha predict --curated data_curated \
   --model artifacts/alpha_model.json --out artifacts/alpha_scores.csv
```

Steps:

1. Load curated panel.
2. Rebuild feature matrix for artifact feature list (`allow_future_leak=True` to use last observed values).
3. Isolate most recent date, score each ticker, write CSV sorted by descending score.

CSV schema: `ticker,score`.

### Programmatic Usage

```python
from src.ai.dataset import assemble_training_set
from src.data.registry import get_registry
reg = get_registry('data_curated')
panel = reg.load_all()
X,y = assemble_training_set(panel, horizon=1, feature_prefixes=['fundamentals_','fx_rates_'])
```

`X` is a (date,ticker) indexed DataFrame; `y` a future return Series with identical index alignment (after intersection). Use any external ML stack (LightGBM, sklearn) if desired—artifact spec is intentionally simple.

### Integration Roadmap

| Stage   | Enhancement                                                                 | Rationale                                    |
| ------- | --------------------------------------------------------------------------- | -------------------------------------------- |
| 1 (now) | Linear OLS                                                                  | Transparent baseline                         |
| 2       | Add z‑scoring / per‑date standardization flag to CLI                        | Normalize cross‑section for scale robustness |
| 3       | Add LightGBM option (reuse existing optional dependency from `ai_model`)    | Non‑linear interactions                      |
| 4       | Walk‑forward temporal split utilities                                       | Realistic OOS validation                     |
| 5       | Signal → Backtest bridge (convert predicted scores to weights & run engine) | Unified performance evaluation               |

### Backtest Integration (Planned)

A forthcoming helper will transform latest prediction scores into a rank‑based (or z‑scored) signal Series compatible with `engine.backtest`, enabling comparative evaluation vs DSL‑generated formulas under identical cap/lev/cost settings.

---

## Artifact Directory Structure & API Integration (FastAPI Ready)

To avoid clutter and provide a stable contract for a forthcoming FastAPI service, all generated files are organized under `artifacts/` with predefined subdirectories (override root via `QUANT_ARTIFACT_ROOT`).

```
artifacts/
   logs/         # Streaming JSONL (ai_run --jsonl, future evaluation logs)
   reports/      # Summary JSON (ai_mvp report, QA summaries)
   models/       # Trained model artifacts (linear_cs, LightGBM)
   datasets/     # Feature/label parquet datasets (alpha builds)
   signals/      # Prediction CSVs from ai_alpha predict
   strategies/   # Exported strategy selections, equity curves (future)
```

Centralized path helpers: `src/config/paths.py`

Example:
```python
from src.config.paths import path, ensure
reports_dir = path('reports')
out = ensure('signals', 'latest_scores.csv')
```

Server-side utilities (for FastAPI integration): `src/server/artifacts.py` exposes:

| Function | Purpose |
|----------|---------|
| `list_reports()` | Enumerate report JSON files |
| `get_report(name)` | Load a specific report JSON |
| `list_logs()` | List JSONL log files |
| `tail_log(name, n)` | Last N lines of a log (streaming preview) |
| `list_models()` | List model artifacts |
| `list_datasets()` | List dataset directories |

### FastAPI Integration Outline

Planned endpoints (examples):

| Endpoint | Source | Description |
|----------|--------|-------------|
| `GET /api/reports` | `list_reports()` | Summary report names |
| `GET /api/reports/{file}` | `get_report()` | Report contents (JSON) |
| `GET /api/logs` | `list_logs()` | Available logs |
| `GET /api/logs/{file}?tail=200` | `tail_log()` | Tail lines for live view |
| `GET /api/models` | `list_models()` | Available model artifacts |
| `GET /api/datasets` | `list_datasets()` | Dataset directories |
| `GET /api/panel/slice?from=YYYY-MM-DD&to=YYYY-MM-DD&ticker=ERIC` | Parquet (registry) | Serve panel slices for charting |
| `GET /api/strategy/{hash}/equity` | SQLite (`run_returns`) | Return daily equity curve |

The FastAPI layer will:
1. Use registry (`get_registry`) to read parquet panel slices for time series graphs (prices, factor series, ensemble equity recomputation).
2. Surface JSON artifacts (reports, models) for UI dashboards without duplication.
3. Stream incremental JSONL logs for real-time training/backtest progress.

### Why Serve Directly From Parquet?

- Avoids duplicating large panel data in serialized APIs.
- Enables parameterized slicing (date range, subset of tickers) with minimal overhead.
- Keeps backend stateless aside from cached registry object (warm in-memory DataFrame or lazy future alternative).

### Future Enhancements

| Area | Enhancement |
|------|-------------|
| Security | Add whitelist + size limits for slice queries |
| Caching | ETag / last-mod for model & report downloads |
| Streaming | WebSocket tail for logs and progress events |
| Visualization | Pre-aggregated parquet metrics (vol/drawdown) for faster charts |
| Governance | Embed data_version + model hash in every response header |

---

---

---

## Persistence Layer (SQLite) for Model Training

Generated & backtested expressions are persisted to a SQLite database (`runs` table) for downstream analytics / ML ranking.

### Daily Net Return Series (run_returns side table)

In addition to summary backtest metrics, each strategy's per-day net return path is stored in a companion table `run_returns` to enable richer downstream modeling (e.g., drawdown features, volatility clustering, regime labeling, autocorrelation diagnostics) without re-running backtests.

Schema:

| Column | Description                          |
| ------ | ------------------------------------ |
| run_id | Foreign key → `runs.id`              |
| date   | String (ISO date or trading key)     |
| net    | Net return for that run_id, that day |

Constraints:

- Primary Key `(run_id, date)` ensures idempotent inserts.
- `FOREIGN KEY(run_id)` references `runs(id)` with `ON DELETE CASCADE`.
- Population uses `INSERT OR IGNORE` so re-processing a duplicate expression hash does not duplicate daily rows.

Example query – reconstruct full equity curve for top Sharpe strategies:

```sql
WITH ranked AS (
   SELECT id, expr, bt_ann_sharpe
   FROM runs
   WHERE error IS NULL
   ORDER BY bt_ann_sharpe DESC
   LIMIT 5
)
SELECT r.expr, rr.date, rr.net
FROM ranked r
JOIN run_returns rr ON rr.run_id = r.id
ORDER BY r.bt_ann_sharpe DESC, rr.date ASC;
```

Compute rolling drawdown stats (SQLite example with window emulation):

```sql
-- Export to Python / DuckDB for richer window ops is recommended; minimal SQLite example:
SELECT run_id,
          date,
          SUM(net) OVER (PARTITION BY run_id ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_ret
FROM run_returns;
```

Programmatic access (Python):

```python
import sqlite3, pandas as pd
conn = sqlite3.connect('runs.sqlite')
df_daily = pd.read_sql_query(
      "SELECT run_id, date, net FROM run_returns WHERE run_id IN (SELECT id FROM runs WHERE error IS NULL ORDER BY bt_ann_sharpe DESC LIMIT 10)",
      conn,
      parse_dates=['date']
)
```

Modeling ideas enabled:

1. Label engineering: rolling Sharpe, volatility, max drawdown per horizon.
2. Regime clustering: feed standardized daily curves into HMM / k-means.
3. Early stopping heuristics: detect unstable equity paths quickly.
4. Residualization: regress daily returns against market factors to derive alpha decay.

Future enhancements (planned): compress daily series to Parquet for faster bulk I/O; add gross returns & cost components; store evaluation environment hashes (data version, cost model version) for full reproducibility.

### Schema (runs)

| Column                              | Description                                            |
| ----------------------------------- | ------------------------------------------------------ |
| expr                                | Original DSL text                                      |
| expr_hash                           | Structural hash of optimized AST (dedup key)           |
| complexity_score                    | Weighted complexity score                              |
| cx\_\*                              | Individual complexity metrics (nodes, depth, etc.)     |
| parse_s / eval_s                    | (Reserved) evaluation timings (parse currently unused) |
| bt_days                             | Number of backtest days                                |
| bt_net_cum / bt_gross_cum           | Cumulative net / gross returns                         |
| bt_ann_sharpe                       | Annualized Sharpe of net returns                       |
| bt_avg_turnover                     | Mean daily turnover                                    |
| bt_avg_gross_lev / bt_max_gross_lev | Leverage stats                                         |
| bt_avg_cost_bps                     | Average daily total cost (bps)                         |
| error                               | Error message if evaluation/backtest failed            |
| params_json                         | JSON parameters (cap, leverage, smoothing, etc.)       |

### Programmatic Use

```python
from src.ai.persist import run_and_persist
result = run_and_persist('ma(5)-ma(10)', df, costs_df, 'runs.sqlite')
print(result.backtest_summary, result.error)
```

### Batch CLI

```bash
python -m src.cli.ai_run --db runs.sqlite --data data_raw/stock_history.csv --n 50 --seed 123
```

Writes (or appends) rows; duplicate expressions (by structural hash) are ignored.

### Querying Examples

```sql
-- Top Sharpe (net) among simplest formulas
SELECT expr, bt_ann_sharpe, complexity_score
FROM runs
WHERE error IS NULL
ORDER BY complexity_score ASC, bt_ann_sharpe DESC
LIMIT 20;

-- Complexity vs performance scatter (export)
SELECT complexity_score, bt_ann_sharpe FROM runs WHERE error IS NULL;
```

### Next Possible Enhancements

- Parquet/Arrow export for vectorized modeling.
- Store per-day returns (net series) in auxiliary table for richer labeling.
- Maintain versioning (data snapshot id, cost model id) for reproducibility.
- Add indices on `(bt_ann_sharpe)` and `(complexity_score)` for faster exploratory queries.
- Lightweight feature importance model training script.

### Results Analysis CLI (`ai_results`)

Inspect and extract persisted strategy results without writing ad‑hoc SQL.

Subcommands:

1. `list` – rank / filter strategies (Sharpe or net) with complexity and turnover context.
2. `equity` – retrieve cumulative equity curve (net) for a given `run_id` or `expr_hash`.
3. `export` – dump `runs` (and optionally joined `run_returns`) to CSV for modeling.

Examples:

```bash
python -m src.cli.ai_results list --db runs.sqlite --limit 30 --no-error --min-days 150
python -m src.cli.ai_results list --db runs.sqlite --format jsonl | jq '.bt_ann_sharpe'
python -m src.cli.ai_results equity --db runs.sqlite --expr-hash abcd1234 --out equity_abcd1234.csv
python -m src.cli.ai_results export --db runs.sqlite --daily --out all_with_daily.csv
```

`list` output columns (subset):

| Column           | Meaning                                                     |
| ---------------- | ----------------------------------------------------------- |
| id / expr_hash   | Primary key / structural hash                               |
| bt_ann_sharpe    | Annualized Sharpe (net)                                     |
| bt_net_cum       | Total cumulative net return (sum of daily net)              |
| bt_days          | Number of backtest days                                     |
| complexity_score | Scalar complexity metric                                    |
| cx_nodes/depth   | Structural size / depth of AST                              |
| bt_avg_turnover  | Mean daily turnover                                         |
| bt_avg_gross_lev | Mean gross leverage                                         |
| bt_avg_cost_bps  | Average total cost in basis points                          |
| ann_vol\*        | (Optional) Annualized volatility: std(daily net)\*sqrt(252) |
| max_dd\*         | (Optional) Maximum drawdown of cumulative net series        |
| error            | Error text if the run failed                                |

(\*) Included only when `--add-vol` / `--add-drawdown` flags are supplied.

Filtering & enrichment flags:

- `--min-days N` only show sufficiently long histories.
- `--max-complexity X` restricts to simpler formulas.
- `--no-error` excludes failed evaluations.
- `--sort sharpe|net` ranking dimension.
- `--add-vol` compute and append annualized volatility column.
- `--add-drawdown` compute and append maximum drawdown column.

Equity retrieval adds a `cum_net` column (cumulative sum of daily net returns) and can write to CSV for external plotting.

Modeling workflow using CLI:

1. Generate + persist: `ai_run`.
2. Triage promising hashes: `ai_results list --no-error --min-days 200 --sort sharpe`.
3. Export equity curves: loop `ai_results equity ...` for top hashes.
4. Bulk dataset for ML: `ai_results export --daily --out training_dataset.csv`.

Planned extensions:

- Add rolling window Sharpe & volatility quantiles to `list`.
- Inline mini sparkline (unicode) for quick visual scan.
- Optional JSON schema validation for downstream pipelines.

---

## Automatic Dynamic Feature Discovery (Data-Agnostic Mode)

The AI search no longer relies on a static, hand‑curated list of DSL feature terminals. Instead it builds a **dynamic feature catalog** each run from the fully merged curated dataset. Every _numeric_ column that passes basic quality filters becomes addressable via the generic terminal form:

```
feat("<column_name>")
```

### Build Pipeline

1. Load all curated domains using the strict registry (`reg.load_all()`), yielding a wide DataFrame with columns combining bars, fundamentals, FX, costs, universe flags, and any generic domains.
2. For each column:
   - Skip bookkeeping / ignored names (`date`, `ticker`, plus `ignore_columns` from `configs/data.yaml`).
   - Skip non-numeric dtypes.
   - Compute non‑null ratio; require ≥ configurable threshold (default 0.40).
   - Compute variance; require ≥ `1e-12` to exclude near-constants.
   - Infer domain from prefix mapping (e.g. `fundamentals_` → `fundamentals`, `fx_rates_` → `fx`).
   - Attach configured domain lag (see below).
3. Emit `FeatureMeta` records (name, domain, non_null_ratio, variance, distinct count, lag_days, dtype_kind).

If no columns survive filtering the run aborts early (guardrail to avoid wasting search budget on an empty terminal set).

### Domain Lags (Availability / Latency Semantics)

Fundamental and certain reference data arrive with reporting delay. To enforce realistic _as‑of_ access, per‑domain lags are specified in `configs/data.yaml`:

```yaml
domain_lags:
  fundamentals: 2 # shift fundamentals_* columns by 2 trading days within each ticker
  fx: 0
  cost_model: 0
ignore_columns:
  - some_debug_col
```

At runtime each catalog series is **shifted within ticker** by `lag_days` before being exposed through `feat("col")`. This ensures generated expressions cannot (accidentally) peek at unreleased fundamentals. A zero lag leaves series unchanged.

### Resolution Order for `feat()`

The DSL runtime overrides the primitive `feat()` to implement a strict precedence when an expression references `feat("x")`:

1. Dynamic catalog lookup (preferred; applies domain lag automatically).
2. Direct raw DataFrame column (if catalog omission was due to filtering but column still exists and is numeric).
3. Registered static feature primitive (legacy path, e.g. `r1`, `ma`, `atr`).
4. Fallback / error if none matched.

This layering allows seamless mixing of static derived features (e.g. `r1`) and raw catalog columns (`fundamentals_revenues`, `fx_rates_eurseK_close`, etc.) without separate syntactic forms.

### Expression Generation Changes

`ai_run` now constructs a terminal universe from dynamic catalog names and hands it to the generator. Terminals are injected purely as `feat("<name>")` tokens; the generator no longer expands a static whitelist of primitive feature calls. Utilities and operators (e.g. `cs_rank`, `lag`, arithmetic) apply on top of these terminals exactly as before.

### Redundancy Pruning (First Pass)

Immediately after generation a lightweight pruning step removes exact duplicates and whitespace-insensitive duplicates (structural normalization by stripping all whitespace). Correlation / structural equivalence pruning is planned but intentionally deferred to keep the baseline transparent and fast.

### Synthetic OHLC Fallback (Transitional)

Some legacy primitives (ATR, gap, spread) expect a full OHLC set (`o_sek`, `h_sek`, `l_sek`, `c_sek`). Curated data presently only guarantees `px_close`. To avoid widespread generator failures during early AI exploration:

- If `c_sek` missing but `px_close` present → alias `c_sek = px_close`.
- Missing `o_sek` / `h_sek` / `l_sek` → neutral copies of `c_sek` (these primitives then degenerate to zero or null volatility signals, which is acceptable for bootstrapping but not for production modeling).

These fallbacks live in both the primitives layer and PnL path. They will be **deprecated** once proper adjusted OHLC fields land in the curated contract. Until then, low information content from ATR/spread/gap is expected and not an error.

### Typical `ai_run` Flow (Curated Mode)

```powershell
python -m src.cli.ai_run --db runs.sqlite --n 50 --seed 123
```

Internal steps:

1. Registry loads all strict-contract parquet domains.
2. Synthetic OHLC fallback applied if necessary.
3. Feature catalog built → dynamic terminals list.
4. Random expressions generated (depth limit, complexity scoring) using only those terminals.
5. Redundancy pruning.
6. Each expression evaluated & backtested; results persisted to SQLite (`runs` + daily `run_returns`).
7. Progress printed with live Sharpe (or reason for missing metrics).

### Inspecting Catalog Programmatically

```python
from src.ai.feature_catalog import build_feature_catalog
from src.data.registry import get_registry
reg = get_registry('data_curated', raw_root='data_raw')
df = reg.load_all()
catalog = build_feature_catalog(df, domain_lags={'fundamentals':2})
for m in catalog[:10]:
      print(m.name, m.domain, m.lag_days, f"nnr={m.non_null_ratio:.2f}")
```

### Design Rationale

| Problem                                 | Old Behavior                             | New Dynamic Catalog Benefit                   |
| --------------------------------------- | ---------------------------------------- | --------------------------------------------- |
| Expanding data sources                  | Manual primitive additions               | Auto-onboarding of any numeric curated column |
| Fundamentals latency enforcement        | Ad hoc shifting in hand-written formulas | Centralized per-domain lag application        |
| Feature space transparency              | Implicit, scattered across code          | Single introspectable `FeatureMeta` list      |
| Guarding against dead / constant fields | None                                     | Variance & non-null filters prune noise       |
| AI search adaptability                  | Static set, brittle to schema evolution  | Schema-driven, resilient to new domains       |

### Future Enhancements (Planned)

| Area                | Idea                                                           |
| ------------------- | -------------------------------------------------------------- |
| Quality Filters     | Add staleness (days since last change) & entropy thresholds    |
| Correlation Pruning | Pre-compute pairwise corr; drop > 0.98 duplicates              |
| Importance Seeding  | Rank terminals by historical standalone Sharpe / stability     |
| Domain Budgeting    | Cap proportion of fundamentals vs price vs exogenous terminals |
| Lag Simulation      | Support alternate lag scenarios (what-if fundamentals faster)  |
| Catalog Persistence | Cache per data_version hash for reproducibility & diffing      |

---

© 2025
