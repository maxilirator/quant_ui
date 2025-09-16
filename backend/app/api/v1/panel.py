from __future__ import annotations

"""Panel slice utilities (read-only).

Loads a narrow slice of the curated parquet panel (bars_eod) for charting.
Downsamples large responses to a fixed row cap.
"""
from pathlib import Path
from typing import Sequence, Dict, Any
import math
import duckdb

MAX_ROWS = 25_000


def load_panel_slice(
    curated_root: str | Path,
    start: str | None,
    end: str | None,
    tickers: Sequence[str] | None,
) -> Dict[str, Any]:
    root = Path(curated_root)
    # Minimal existence check
    if not list(root.glob("bars_eod/ticker=*/year=*/*.parquet")):
        return {
            "rows": [],
            "columns": ["date", "ticker", "px_close"],
            "total_rows": 0,
            "downsampled": False,
        }

    bars_glob = str(root / "bars_eod" / "ticker=*" / "year=*" / "*.parquet")
    where_parts = []
    if start:
        where_parts.append(f"date >= '{start}'")
    if end:
        where_parts.append(f"date <= '{end}'")
    if tickers:
        quoted = ",".join(f"'{t}'" for t in tickers)
        where_parts.append(f"ticker IN ({quoted})")
    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    query = f"""
    WITH bars AS (
      SELECT date, ticker, c_raw AS px_close
      FROM read_parquet('{bars_glob}')
    )
    SELECT date, ticker, px_close
    FROM bars
    {where_sql}
    ORDER BY date, ticker
    """
    con = duckdb.connect()
    con.execute("PRAGMA threads=2")
    df = con.execute(query).fetch_df()
    total_rows = len(df)
    downsampled = False
    if total_rows > MAX_ROWS and total_rows > 0:
        stride = math.ceil(total_rows / MAX_ROWS)
        df = df.iloc[::stride]
        downsampled = True
    return {
        "rows": df.to_dict(orient="records"),
        "columns": list(df.columns),
        "total_rows": total_rows,
        "downsampled": downsampled,
    }


__all__ = ["load_panel_slice"]
