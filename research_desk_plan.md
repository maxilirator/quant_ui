# Research Desk Plan (q-training data)

## Goal
Build a lightweight web-based research desk for **fast visual inspection and anomaly detection** on the `data/xsto` stack. The app reads existing data only (no mutation), and exposes a small Starlette API with a Shoelace + TradingView Lightweight Charts frontend.

## Non-Goals
- No model training or backtesting here.
- No data generation; this is a **read-only** inspection tool.

## Data Inventory (q-training)
All paths are repo-relative unless noted.

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
- `configs/paths.yaml` (data_root, MLflow, Optuna, etc.)
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
Returns available feature names from DuckDB views:
- Alpha360 features + liquidity + sector + vol + exogenous + flags.
- Provide `source` and `dtype` if available.

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

### Coverage guard (per response)
For requested fields:
- If all values are NaN for a date, mark it in response metadata.
- Include a per-field `missing_ratio` in JSON (for quick diagnostics).

### Instrument validity
If ticker is delisted, enforce `all.txt` end-date:
- If `to` > end_date, return error or clip with warning (configurable).

## UI Plan
Shoelace + TradingView Lightweight Charts:

### Panels
- **Ticker selector** (searchable).
- **Date range** with calendar alignment warning.
- **Bars chart** (OHLCV).
- **Feature overlays** (selectable list).
- **Diagnostics panel**: missing ratios, blackout stats, non-tradable ratios, sector label.

### Quick anomaly widgets
- Missing bars per day
- NaN ratio per feature
- Sudden shifts vs 7d/30d mean

## Implementation Steps

1. **Repository setup**
   - Starlette app + minimal router.
   - Single DuckDB connection (read-only).
   - qlib init using `data/xsto` provider.

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

## Future Extensions (optional)
- Cross-instrument comparison panel
- Sector aggregation (HHI, exposure)
- Audit screens for missing OHLCV vs blackout flags
