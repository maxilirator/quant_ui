from __future__ import annotations

from dataclasses import dataclass

import duckdb

from app.paths import DataPaths

RESERVED_COLUMNS = {"instrument", "ticker", "datetime", "date", "time"}
INSTRUMENT_COLUMNS = ("instrument", "ticker")
DATE_COLUMNS = ("datetime", "date")


VIEW_SPECS = {
    "alpha360": "market_neutral_alpha360",
    "features_vol": "features_vol",
    "features_liquidity": "features_liquidity",
    "features_sector": "features_sector",
    "exogenous_fx": "exogenous_fx",
    "exogenous_daily": "exogenous_daily",
}


@dataclass
class DuckDBState:
    conn: duckdb.DuckDBPyConnection
    views: list[str]
    missing_views: dict[str, str]
    view_schema: dict[str, dict[str, str]]
    feature_sources: dict[str, str]
    instrument_columns: dict[str, str]
    datetime_columns: dict[str, str]


def _describe_view(conn: duckdb.DuckDBPyConnection, view_name: str) -> dict[str, str]:
    rows = conn.execute(f"DESCRIBE {view_name}").fetchall()
    return {row[0]: row[1] for row in rows}


def init_duckdb(paths: DataPaths) -> DuckDBState:
    conn = duckdb.connect(database=":memory:")
    views: list[str] = []
    missing: dict[str, str] = {}
    view_schema: dict[str, dict[str, str]] = {}
    feature_sources: dict[str, str] = {}
    instrument_columns: dict[str, str] = {}
    datetime_columns: dict[str, str] = {}

    for view_name, attr_name in VIEW_SPECS.items():
        path = getattr(paths, attr_name)
        if path.exists():
            conn.execute(
                f"CREATE VIEW {view_name} AS SELECT * FROM '{path.as_posix()}'"
            )
            views.append(view_name)

            schema = _describe_view(conn, view_name)
            view_schema[view_name] = schema
            columns = list(schema.keys())

            instrument_col = next(
                (name for name in INSTRUMENT_COLUMNS if name in columns), None
            )
            datetime_col = next((name for name in DATE_COLUMNS if name in columns), None)
            if instrument_col:
                instrument_columns[view_name] = instrument_col
            if datetime_col:
                datetime_columns[view_name] = datetime_col

            for column in columns:
                if column in RESERVED_COLUMNS:
                    continue
                if column not in feature_sources:
                    feature_sources[column] = view_name
        else:
            missing[view_name] = str(path)

    return DuckDBState(
        conn=conn,
        views=views,
        missing_views=missing,
        view_schema=view_schema,
        feature_sources=feature_sources,
        instrument_columns=instrument_columns,
        datetime_columns=datetime_columns,
    )
