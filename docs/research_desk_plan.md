# Research Desk Plan (q-training data)

## Goal
Build a lightweight web-based research desk for **fast visual inspection and anomaly detection** on the `data/xsto` stack. The app reads existing data only (no mutation), and exposes a small Starlette API with a Shoelace + TradingView Lightweight Charts frontend.

## Non-Goals
- No model training or backtesting here.
- No data generation; this is a **read-only** inspection tool.

## Data Inventory (q-training)
All paths are repo-relative unless noted. `configs/paths.yaml` stores an absolute `data_root`.

### Core calendars / instruments
- `data/xsto/calendars/day.txt`  
  Canonical trading calendar (one date per line, YYYY-MM-DD).
- `data/xsto/instruments/all.txt`  
  Canonical equities universe with start/end dates per instrument.
- `data/xsto/instruments/indexes.txt`  
  Index instruments (e.g., `omxs30`, `xact-omxs30`).

### Market bars (qlib bin files)
Stored per instrument (for OHLCV and related fields):
- `data/xsto/features/<instrument>/*.day.bin`  
  Example fields: `open`, `high`, `low`, `close`, `volume`, `turnover`, etc.  
  Use qlib `D.features(...)` or qlib's file reader to materialize.

### Feature parquets
MultiIndex `(instrument, datetime)` or `(datetime, instrument)` depending on generator; normalize to `(instrument, datetime)` in the API layer.
- `data/xsto/market_neutral_features/market_neutral_alpha360.parquet`  
  Alpha360 + market neutral + liquidity/cost features + `blackout_flag` / `non_tradable`.
- `data/xsto/features_vol.parquet`
- `data/xsto/features_liquidity.parquet`
- `data/xsto/features_sector.parquet`

### Meta / sidecar data
- `data/xsto/meta/sector_map.parquet`  
  Sector/industry mapping from EODHD fundamentals.
- `data/xsto/meta/instrument_blackouts.parquet`  
  Instrument blackout days used to mask missing/invalid bars.
- `data/xsto/exogenous/fx.parquet`
- `data/xsto/exogenous/exog_daily.parquet` (if present)

### Configs that describe paths / behavior
- `configs/paths.yaml` (absolute `data_root` only; other paths are derived in code; allow `DATA_ROOT` override)
- `configs/feature_build.yaml` (feature generation settings)
- `configs/fill_policy.yaml` (fill policy expectations)

## Data Access Strategy

### 1) DuckDB for Parquet feature data
Use DuckDB to query large parquets efficiently:
- `market_neutral_alpha360.parquet`
- `features_vol.parquet`
- `features_liquidity.parquet`
- `features_sector.parquet`
- exogenous/fx/parquets

Create DuckDB views:
```
CREATE VIEW alpha360 AS SELECT * FROM 'data/xsto/market_neutral_features/market_neutral_alpha360.parquet';
CREATE VIEW features_vol AS SELECT * FROM 'data/xsto/features_vol.parquet';
CREATE VIEW features_liquidity AS SELECT * FROM 'data/xsto/features_liquidity.parquet';
CREATE VIEW features_sector AS SELECT * FROM 'data/xsto/features_sector.parquet';
```

Normalize to `(instrument, datetime)` ordering in API responses.

### 2) Qlib for OHLCV bins
OHLCV should come from qlib `D.features(...)` for consistent pricing:
- `D.features(instruments=[ticker], fields=["$open", "$high", "$low", "$close", "$volume"], start_time, end_time, freq="day")`

This avoids hand-parsing `*.day.bin` and respects qlib’s layout.

### 3) Calendar alignment
Use `data/xsto/calendars/day.txt` as the **source of truth**.  
All API responses should align to this calendar (or use it for validation).

## API Endpoints

### GET /tickers
Returns canonical tickers from `instruments/all.txt` and `indexes.txt`.
- Include `start`, `end`, `type` (equity/index).
- Optionally add flags: `instruments_only`, `indexes_only`.

### GET /features
Returns available feature names from DuckDB views (no `ticker` provided):
- Alpha360 features + liquidity + sector + vol + exogenous + flags.
- Provide `source` and `dtype` if available.
- Filters: `q` (substring search), `source` (view name), `limit`.
- Response includes `count`, `matched`, and `total`.

### GET /bars?ticker&from&to
Returns OHLCV from qlib:
- `from`/`to` inclusive (calendar-aware).
- Must validate ticker against `all.txt` or `indexes.txt`.
- Add optional `adjusted`? (if used in qlib)

### GET /features?ticker&from&to&names=
Returns time series for specified features:
- `names` is comma-separated list.
- Pull from DuckDB views (alpha360 first, then sidecars).
- Normalize datetime column to ISO date.
- Enforce `names` exist; fail fast on missing.

## Data Consistency Guards

### Calendar guard
For any query window:
- Check `from`/`to` present in `day.txt`.
- If outside, return error with guidance.
- Enforce calendar alignment by using `day.txt` as the source of truth for valid dates; responses include only calendar dates and report gaps in `meta.missing_dates`.

### Coverage guard (per response)
For requested fields:
- If all values are NaN for a date, mark it in response metadata.
- Include a per-field `missing_ratio` in JSON (for quick diagnostics).

### Instrument validity
If ticker is delisted, enforce `all.txt` end-date:
- If `to` > end_date, return error (configurable).
- If `from` < start_date, return error.

## UI Plan
Shoelace + TradingView Lightweight Charts (desktop-only, no mobile layout):

### Panels
- **Ticker selector** (searchable).
- **Date range** with calendar alignment warning.
- **Bars chart** (OHLCV) with **fixed volume subpanel**.
- **Feature overlays** (selectable list) on a **secondary axis**; no hard limit on overlays.
- **Diagnostics panel** (collapsible): missing ratios, blackout stats, non-tradable ratios, sector label.

### Quick anomaly widgets (bottom strip)
- Missing bars per day
- NaN ratio per feature
- Sudden shifts vs 7d/30d mean
- Calendar warnings appear here only.

### Interaction / Theme
- No hover table initially; consider click-to-table later if needed.
- Visual direction: trading desk, dark theme.

## Implementation Steps

1. **Repository setup**
   - Python backend managed via `pyproject.toml`.
   - App code lives under `app/`.
   - Load absolute `data_root` from `configs/paths.yaml` with `DATA_ROOT` override.
   - Starlette app + minimal router.
   - Cache qlib init at startup using the resolved `data_root`.
   - Single DuckDB connection (read-only).

2. **Data loaders**
   - `load_calendar()` from `day.txt`
   - `load_instruments()` from `all.txt` and `indexes.txt`
   - `duckdb_views()` for parquets
   - `qlib_bars()` for OHLCV

3. **API handlers**
   - `/tickers`, `/features`, `/bars`, `/features` (by name)
   - Strict validation & consistent JSON schema

4. **Front-end**
   - Plain HTML + Shoelace
   - Lightweight Charts for OHLC
   - Feature overlay lines
   - Served from the Starlette app static directory

5. **Diagnostics**
   - Missing ratios
   - Calendar mismatch warnings
   - Blackout/non-tradable overlay indicator (if feature present)

## Suggested JSON Schemas

### /bars
```
{
  "ticker": "abb",
  "from": "2024-01-01",
  "to": "2024-12-31",
  "calendar_aligned": true,
  "bars": [
    {"date": "2024-01-02", "open": 123.4, "high": 126.0, "low": 121.8, "close": 124.5, "volume": 123456}
  ],
  "meta": {
    "missing_dates": [],
    "missing_ratio": {"open": 0.0, "high": 0.0, "low": 0.0, "close": 0.0, "volume": 0.0},
    "source": "qlib"
  }
}
```

### /features
```
{
  "ticker": "abb",
  "from": "2024-01-01",
  "to": "2024-12-31",
  "features": {
    "adv_sek_30d": [{"date": "...", "value": 123.0}],
    "asset_vol_20d": [{"date": "...", "value": 0.12}]
  },
  "meta": {
    "missing_ratio": {"adv_sek_30d": 0.05},
    "sources": {"adv_sek_30d": "features_liquidity"}
  }
}
```

## Notes / Key Decisions
- **Do not** mutate data. Any fixes happen in q-training scripts only.
- Use `day.txt` as the only calendar authority.
- Prefer **qlib** for OHLCV (bin files), **DuckDB** for features (parquet).
- Fail fast on unknown tickers or missing features.
- All API dates use ISO `YYYY-MM-DD`.
- Normalize tickers to lowercase on input/output; feature names remain case-sensitive.

## Future Extensions (optional)
- Cross-instrument comparison panel
- Sector aggregation (HHI, exposure)
- Audit screens for missing OHLCV vs blackout flags
