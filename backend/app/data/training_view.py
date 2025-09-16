"""DuckDB training_view materialization scaffold.

The goal is to unify bars, universe, FX, and costs into a single wide view
in SEK terms. This initial version defines a function signature and a simple
join placeholder to be expanded.
"""

from __future__ import annotations

from pathlib import Path
import duckdb
import pandas as pd
from typing import Optional


def build_training_view(
    curated_root: str | Path,
    limit_tickers: Optional[int] = None,
    year_filter: Optional[int] = None,
) -> pd.DataFrame:
    """Load core parquet domains and produce a minimal merged frame.

    Parameters
    ----------
    curated_root: Root directory of curated parquet dataset.
    limit_tickers: If provided, restrict to first N tickers (performance/debug).
    year_filter: Optional year to filter bars_universe subset.
    """
    root = Path(curated_root)
    con = duckdb.connect()

    bars_glob = str(root / "bars_eod" / "ticker=*/year=*/*.parquet")
    universe_glob = str(root / "universe_membership" / "year=*/*.parquet")
    fx_glob = str(root / "fx_rates" / "ccy_pair=*/*.parquet")
    cost_glob = str(root / "cost_model_daily" / "year=*/*.parquet")
    cal_glob = str(root / "trading_calendar" / "year=*/*.parquet")

    # Basic existence check (silent skip if absent)
    def _exists_any(pattern: str) -> bool:
        return len(list(Path().glob(pattern))) > 0

    selects = []
    if _exists_any(bars_glob):
        selects.append(
            f"bars AS (SELECT date, ticker, c_raw AS px_close FROM read_parquet('{bars_glob}'))"
        )
    if _exists_any(universe_glob):
        selects.append(
            f"universe AS (SELECT date, ticker, 1 AS in_universe FROM read_parquet('{universe_glob}'))"
        )
    if _exists_any(fx_glob):
        selects.append(
            f"fx AS (SELECT date, ccy_pair, close FROM read_parquet('{fx_glob}'))"
        )
    if _exists_any(cost_glob):
        selects.append(
            f"costs AS (SELECT date, ticker, commission_bps, half_spread_bps FROM read_parquet('{cost_glob}'))"
        )
    if _exists_any(cal_glob):
        selects.append(f"cal AS (SELECT date, is_open FROM read_parquet('{cal_glob}'))")

    ctes = ",\n".join(selects)
    if not ctes:
        return pd.DataFrame()

    query = f"""
    WITH
    {ctes}
    SELECT b.date, b.ticker, b.px_close,
           COALESCE(u.in_universe, 0) AS in_universe,
           c.commission_bps,
           c.half_spread_bps
    FROM bars b
    LEFT JOIN universe u USING(date, ticker)
    LEFT JOIN costs c USING(date, ticker)
    -- FX & calendar integration TBD
    """
    df = con.execute(query).fetch_df()
    if limit_tickers:
        tickers = sorted(df["ticker"].unique())[:limit_tickers]
        df = df[df["ticker"].isin(tickers)]
    if year_filter and "date" in df.columns:
        df = df[df["date"].str.startswith(str(year_filter))]
    return df


__all__ = ["build_training_view"]
