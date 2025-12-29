from __future__ import annotations

from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Optional

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from app.calendar import build_calendar_index, load_calendar, slice_calendar
from app.duckdb import init_duckdb
from app.instruments import load_instruments
from app.paths import load_paths, validate_paths
from app.qlib_init import init_qlib


STATIC_DIR = Path(__file__).resolve().parent / "static"
FEATURE_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "configs" / "feature_settings.json"


def _parse_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _coerce_feature_settings(payload: object) -> dict[str, dict[str, object]]:
    if isinstance(payload, dict) and "features" in payload:
        payload = payload.get("features")
    if not isinstance(payload, dict):
        return {}

    settings: dict[str, dict[str, object]] = {}
    for name, raw in payload.items():
        if not isinstance(name, str):
            continue
        color = raw
        if isinstance(raw, dict):
            color = raw.get("color")
        if isinstance(color, str) and color:
            settings[name] = {"color": color}
    return settings


def _load_feature_settings(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return _coerce_feature_settings(payload)


def _save_feature_settings(path: Path, settings: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"features": settings}
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _load_sector_map(
    path: Path, conn
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, list[str]],
    dict[str, dict[str, str]],
    dict[str, str],
]:
    if not path.exists():
        return {}, {}, {}

    query = (
        f"SELECT ticker, sector, industry, start_date, end_date "
        f"FROM '{path.as_posix()}'"
    )
    rows = conn.execute(query).fetchall()

    instrument_meta: dict[str, dict[str, str]] = {}
    sector_to_tickers: dict[str, list[str]] = {}
    sector_bounds: dict[str, dict[str, str]] = {}
    sector_representative: dict[str, str] = {}
    sector_rep_start: dict[str, str] = {}

    for ticker, sector, industry, start_date, end_date in rows:
        ticker_text = str(ticker).lower()
        sector_text = str(sector).strip() if sector is not None else ""
        industry_text = str(industry).strip() if industry is not None else ""
        if sector_text:
            sector_to_tickers.setdefault(sector_text, []).append(ticker_text)
            bounds = sector_bounds.setdefault(sector_text, {"start": "", "end": ""})
            start_norm = _normalize_date(start_date) if start_date else ""
            end_norm = _normalize_date(end_date) if end_date else ""
            if start_norm and (not bounds["start"] or start_norm < bounds["start"]):
                bounds["start"] = start_norm
            if end_norm and (not bounds["end"] or end_norm > bounds["end"]):
                bounds["end"] = end_norm
            if start_norm:
                current_start = sector_rep_start.get(sector_text)
                if not current_start or start_norm < current_start:
                    sector_rep_start[sector_text] = start_norm
                    sector_representative[sector_text] = ticker_text
        instrument_meta[ticker_text] = {
            "sector": sector_text,
            "industry": industry_text,
        }

    return instrument_meta, sector_to_tickers, sector_bounds, sector_representative


def _build_index_definitions(
    market_indexes: list[dict],
) -> tuple[list[dict], dict[str, dict[str, str]]]:
    index_list: list[dict] = []
    index_defs: dict[str, dict[str, str]] = {}

    for item in market_indexes:
        ticker = item["ticker"]
        entry = {
            "id": ticker,
            "label": ticker,
            "kind": "market",
            "start": item.get("start") or "",
            "end": item.get("end") or "",
        }
        index_list.append(entry)
        index_defs[ticker] = {"kind": "market", "ticker": ticker}

    return index_list, index_defs


def _first_available_date(values: dict[str, object], calendar: list[str]) -> Optional[str]:
    for day in calendar:
        value = values.get(day)
        if value is None:
            continue
        return day
    return None


def _load_close_series(ticker: str, start: str, end: str) -> dict[str, float]:
    try:
        from qlib.data import D
    except ImportError as exc:
        raise RuntimeError("qlib is not available") from exc

    data = D.features(
        instruments=[ticker],
        fields=["$close"],
        start_time=start,
        end_time=end,
        freq="day",
    )
    if data is None or getattr(data, "empty", True):
        return {}

    frame = data.reset_index()
    date_col = "datetime" if "datetime" in frame.columns else "date"
    if date_col not in frame.columns:
        return {}
    close_col = "$close" if "$close" in frame.columns else "close"
    if close_col not in frame.columns:
        return {}

    series: dict[str, float] = {}
    for row in frame.itertuples(index=False):
        record = dict(zip(frame.columns, row))
        date_value = _normalize_date(record[date_col])
        close = _normalize_value(record[close_col])
        if _is_missing(close):
            continue
        series[date_value] = close
    return series


def _build_target_map(
    instruments: list[str],
    start: str,
    end: str,
    horizon_days: int,
    target: str,
    calendar_dates: list[str],
    calendar_index: dict[str, int],
) -> tuple[dict[str, dict[str, float]], list[str]]:
    if horizon_days < 0:
        raise ValueError("horizon_days must be non-negative")

    try:
        from qlib.data import D
    except ImportError as exc:
        raise RuntimeError("qlib is not available") from exc

    calendar = slice_calendar(calendar_dates, calendar_index, start, end)
    if not calendar:
        return {}, []
    if horizon_days > 0:
        valid_dates = calendar[: -horizon_days]
    else:
        valid_dates = calendar

    data = D.features(
        instruments=instruments,
        fields=["$open", "$close"],
        start_time=start,
        end_time=end,
        freq="day",
    )
    if data is None or getattr(data, "empty", True):
        return {}, valid_dates

    frame = data.reset_index()
    date_col = "datetime" if "datetime" in frame.columns else "date"
    instrument_col = "instrument" if "instrument" in frame.columns else "ticker"
    open_col = "$open" if "$open" in frame.columns else "open"
    close_col = "$close" if "$close" in frame.columns else "close"
    if date_col not in frame.columns or instrument_col not in frame.columns:
        return {}, valid_dates
    if open_col not in frame.columns or close_col not in frame.columns:
        return {}, valid_dates

    open_map: dict[str, dict[str, float]] = {}
    close_map: dict[str, dict[str, float]] = {}
    for row in frame.itertuples(index=False):
        record = dict(zip(frame.columns, row))
        instrument = str(record[instrument_col]).lower()
        date_value = _normalize_date(record[date_col])
        open_value = _normalize_value(record[open_col])
        close_value = _normalize_value(record[close_col])
        if not _is_missing(open_value):
            open_map.setdefault(instrument, {})[date_value] = float(open_value)
        if not _is_missing(close_value):
            close_map.setdefault(instrument, {})[date_value] = float(close_value)

    target_map: dict[str, dict[str, float]] = {}
    calendar_lookup = {date: idx for idx, date in enumerate(calendar)}
    for instrument in instruments:
        open_series = open_map.get(instrument, {})
        close_series = close_map.get(instrument, {})
        for day in valid_dates:
            day_idx = calendar_lookup.get(day)
            if day_idx is None:
                continue
            future_idx = day_idx + horizon_days
            if future_idx >= len(calendar):
                continue
            future_day = calendar[future_idx]
            close_future = close_series.get(future_day)
            open_future = open_series.get(future_day)

            if target == "ret_cc":
                if close_future is None:
                    continue
                close_now = close_series.get(day)
                if close_now in (None, 0):
                    continue
                value = (close_future / close_now) - 1.0
            elif target == "close_open":
                if close_future is None:
                    continue
                open_now = open_series.get(day)
                if open_now in (None, 0):
                    continue
                value = (close_future / open_now) - 1.0
            elif target == "open_open":
                if open_future is None:
                    continue
                open_now = open_series.get(day)
                if open_now in (None, 0):
                    continue
                value = (open_future / open_now) - 1.0
            else:
                raise ValueError(f"Unknown target: {target}")

            target_map.setdefault(day, {})[instrument] = value

    return target_map, valid_dates


def _resolve_universe(state: Starlette, universe: object) -> list[str]:
    if isinstance(universe, list):
        return [str(item).strip().lower() for item in universe if str(item).strip()]
    if isinstance(universe, str):
        universe_key = universe.strip().lower()
        if universe_key in {"all", "equity", "instruments"}:
            return [item["ticker"] for item in state.instruments_all]
        if universe_key in {"indexes", "index"}:
            return [item["ticker"] for item in state.instruments_indexes]
        return [name.strip().lower() for name in universe_key.split(",") if name.strip()]
    raise ValueError("universe must be a string or list")


def _rolling_metrics(
    dates: list[str], values: list[Optional[float]], window: int
) -> dict[str, list[dict[str, object]]]:
    window = max(int(window), 1)
    rolling_mean: list[dict[str, object]] = []
    rolling_std: list[dict[str, object]] = []
    rolling_ir: list[dict[str, object]] = []
    rolling_t: list[dict[str, object]] = []

    window_values: list[Optional[float]] = []
    for idx, value in enumerate(values):
        window_values.append(value)
        if len(window_values) > window:
            window_values.pop(0)

        valid = [item for item in window_values if item is not None]
        mean = None
        std = None
        ir = None
        t_stat = None
        if valid:
            mean = sum(valid) / len(valid)
            if len(valid) > 1:
                var = sum((item - mean) ** 2 for item in valid) / (len(valid) - 1)
                std = math.sqrt(var)
                if std:
                    ir = mean / std
                    t_stat = mean / (std / math.sqrt(len(valid)))

        day = dates[idx]
        rolling_mean.append({"date": day, "value": mean})
        rolling_std.append({"date": day, "value": std})
        rolling_ir.append({"date": day, "value": ir})
        rolling_t.append({"date": day, "value": t_stat})

    return {
        "ic_mean": rolling_mean,
        "ic_std": rolling_std,
        "ic_ir": rolling_ir,
        "t_stat": rolling_t,
    }


def _error(message: str, status_code: int = 400, details: Optional[object] = None) -> JSONResponse:
    payload = {"error": message}
    if details is not None:
        payload["details"] = details
    return JSONResponse(payload, status_code=status_code)


def _parse_iso_date(value: Optional[str], name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required (YYYY-MM-DD)")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{name} must be YYYY-MM-DD") from exc
    return value


def _parse_optional_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _pearson_corr(values_x: list[float], values_y: list[float]) -> Optional[float]:
    n = len(values_x)
    if n < 2 or n != len(values_y):
        return None
    mean_x = sum(values_x) / n
    mean_y = sum(values_y) / n
    sum_xy = 0.0
    sum_xx = 0.0
    sum_yy = 0.0
    for x, y in zip(values_x, values_y):
        dx = x - mean_x
        dy = y - mean_y
        sum_xy += dx * dy
        sum_xx += dx * dx
        sum_yy += dy * dy
    if sum_xx <= 0 or sum_yy <= 0:
        return None
    return sum_xy / math.sqrt(sum_xx * sum_yy)


def _rank_values(values: list[float]) -> list[float]:
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * n
    idx = 0
    while idx < n:
        start = idx
        value = indexed[idx][1]
        while idx + 1 < n and indexed[idx + 1][1] == value:
            idx += 1
        end = idx
        avg_rank = (start + end) / 2.0 + 1.0
        for pos in range(start, end + 1):
            ranks[indexed[pos][0]] = avg_rank
        idx += 1
    return ranks


def _spearman_corr(values_x: list[float], values_y: list[float]) -> Optional[float]:
    if len(values_x) < 2:
        return None
    ranked_x = _rank_values(values_x)
    ranked_y = _rank_values(values_y)
    return _pearson_corr(ranked_x, ranked_y)


def _decile_means(pairs: list[tuple[float, float]]) -> Optional[list[Optional[float]]]:
    n = len(pairs)
    if n < 10:
        return None
    ordered = sorted(pairs, key=lambda item: item[0])
    buckets: list[list[float]] = [[] for _ in range(10)]
    for idx, (_, target) in enumerate(ordered):
        decile = min(9, int(idx * 10 / n))
        buckets[decile].append(target)
    means: list[Optional[float]] = []
    for bucket in buckets:
        if not bucket:
            means.append(None)
        else:
            means.append(sum(bucket) / len(bucket))
    return means


def _enforce_instrument_window(
    ticker: str,
    start_date: date,
    end_date: date,
    instrument_bounds: dict[str, tuple[Optional[date], Optional[date]]],
) -> None:
    bounds = instrument_bounds.get(ticker)
    if not bounds:
        return
    start_limit, end_limit = bounds
    if start_limit and start_date < start_limit:
        raise ValueError(
            f"from is before instrument start date ({start_limit.isoformat()})"
        )
    if end_limit and end_date > end_limit:
        raise ValueError(
            f"to is after instrument end date ({end_limit.isoformat()})"
        )


def _normalize_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().date().isoformat()
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def _normalize_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    if hasattr(value, "item"):
        return value.item()
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, float) and math.isnan(value)


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def homepage(request: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


async def feature_power_page(request: Request) -> FileResponse:
    return FileResponse(STATIC_DIR / "feature_power.html")


async def health(request: Request) -> JSONResponse:
    state = request.app.state
    return JSONResponse(
        {
            "status": "ok",
            "data_root": str(state.paths.data_root),
            "qlib_initialized": state.qlib_initialized,
            "duckdb_views": state.duckdb.views,
            "duckdb_missing_views": state.duckdb.missing_views,
            "missing_required_paths": state.missing_required_paths,
            "missing_optional_paths": state.missing_optional_paths,
        }
    )


async def tickers(request: Request) -> JSONResponse:
    state = request.app.state
    instruments_only = _parse_bool(request.query_params.get("instruments_only"))
    indexes_only = _parse_bool(request.query_params.get("indexes_only"))

    if instruments_only and not indexes_only:
        tickers = state.instruments_all
    elif indexes_only and not instruments_only:
        tickers = state.instruments_indexes
    elif instruments_only and indexes_only:
        tickers = state.instruments_all + state.instruments_indexes
    else:
        tickers = state.instruments_all

    return JSONResponse({"count": len(tickers), "tickers": tickers})


async def bars(request: Request) -> JSONResponse:
    state = request.app.state
    raw_ticker = request.query_params.get("ticker")
    if not raw_ticker:
        return _error("ticker is required")

    ticker = raw_ticker.strip().lower()
    if not ticker:
        return _error("ticker is required")

    if ticker not in state.ticker_set:
        return _error(
            "Unknown ticker",
            details={"ticker": raw_ticker, "normalized": ticker},
        )

    try:
        start = _parse_iso_date(request.query_params.get("from"), "from")
        end = _parse_iso_date(request.query_params.get("to"), "to")
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
        calendar_dates = slice_calendar(
            state.calendar_dates, state.calendar_index, start, end
        )
    except (ValueError, KeyError) as exc:
        return _error(str(exc))

    try:
        from qlib.data import D
    except ImportError as exc:
        return _error("qlib is not available", status_code=500, details=str(exc))

    fields = ["$open", "$high", "$low", "$close", "$volume"]
    data = D.features(
        instruments=[ticker],
        fields=fields,
        start_time=start,
        end_time=end,
        freq="day",
    )

    bars_by_date: dict[str, dict] = {}
    if data is not None and not getattr(data, "empty", True):
        frame = data.reset_index()
        date_col = "datetime" if "datetime" in frame.columns else "date"
        if date_col not in frame.columns:
            return _error("qlib result missing datetime column", status_code=500)

        field_columns: dict[str, str] = {}
        for field in fields:
            if field in frame.columns:
                field_columns[field] = field
            elif field.lstrip("$") in frame.columns:
                field_columns[field] = field.lstrip("$")
            else:
                return _error(
                    "qlib result missing field",
                    status_code=500,
                    details={"field": field},
                )

        for row in frame.itertuples(index=False):
            record = dict(zip(frame.columns, row))
            date_value = _normalize_date(record[date_col])
            bar = {
                "date": date_value,
                "open": _normalize_value(record[field_columns["$open"]]),
                "high": _normalize_value(record[field_columns["$high"]]),
                "low": _normalize_value(record[field_columns["$low"]]),
                "close": _normalize_value(record[field_columns["$close"]]),
                "volume": _normalize_value(record[field_columns["$volume"]]),
            }
            if all(
                _is_missing(bar[key])
                for key in ("open", "high", "low", "close", "volume")
            ):
                continue
            bars_by_date[date_value] = bar

    field_names = ["open", "high", "low", "close", "volume"]
    missing_counts = {name: 0 for name in field_names}
    for day in calendar_dates:
        bar = bars_by_date.get(day)
        if not bar:
            for name in field_names:
                missing_counts[name] += 1
            continue
        for name in field_names:
            if _is_missing(bar.get(name)):
                missing_counts[name] += 1

    missing_dates = [day for day in calendar_dates if day not in bars_by_date]
    bars_list = [bars_by_date[day] for day in calendar_dates if day in bars_by_date]
    total_dates = len(calendar_dates)
    missing_ratio = {
        name: (missing_counts[name] / total_dates if total_dates else 0.0)
        for name in field_names
    }

    return JSONResponse(
        {
            "ticker": ticker,
            "from": start,
            "to": end,
            "calendar_aligned": True,
            "bars": bars_list,
            "meta": {
                "missing_dates": missing_dates,
                "missing_ratio": missing_ratio,
                "source": "qlib",
            },
        }
    )


async def features(request: Request) -> JSONResponse:
    state = request.app.state
    raw_ticker = request.query_params.get("ticker")

    if not raw_ticker:
        query = request.query_params.get("q")
        source_filter = request.query_params.get("source")
        limit_param = request.query_params.get("limit")
        limit: Optional[int] = None
        if limit_param:
            try:
                limit = int(limit_param)
            except ValueError:
                return _error("limit must be an integer")
            if limit <= 0:
                return _error("limit must be a positive integer")

        query_lower = query.lower() if query else None
        features_list = []
        matched = 0
        total = len(state.duckdb.feature_sources)
        for name in sorted(state.duckdb.feature_sources):
            source = state.duckdb.feature_sources[name]
            if source_filter and source_filter != source:
                continue
            if query_lower and query_lower not in name.lower():
                continue
            matched += 1
            if limit and len(features_list) >= limit:
                continue
            dtype = state.duckdb.view_schema.get(source, {}).get(name)
            features_list.append({"name": name, "source": source, "dtype": dtype})
        return JSONResponse(
            {
                "count": len(features_list),
                "matched": matched,
                "total": total,
                "features": features_list,
            }
        )

    ticker = raw_ticker.strip().lower()
    if not ticker:
        return _error("ticker is required")

    if ticker not in state.ticker_set:
        return _error(
            "Unknown ticker",
            details={"ticker": raw_ticker, "normalized": ticker},
        )

    names_param = request.query_params.get("names")
    if not names_param:
        return _error("names is required when requesting feature data")

    try:
        start = _parse_iso_date(request.query_params.get("from"), "from")
        end = _parse_iso_date(request.query_params.get("to"), "to")
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
        calendar_dates = slice_calendar(
            state.calendar_dates, state.calendar_index, start, end
        )
    except (ValueError, KeyError) as exc:
        return _error(str(exc))

    names = [name.strip() for name in names_param.split(",") if name.strip()]
    if not names:
        return _error("names is required when requesting feature data")

    missing_names = [name for name in names if name not in state.duckdb.feature_sources]
    if missing_names:
        return _error("Unknown feature names", details={"missing": missing_names})

    names_by_view: dict[str, list[str]] = {}
    for name in names:
        view = state.duckdb.feature_sources[name]
        names_by_view.setdefault(view, []).append(name)

    values_by_feature: dict[str, dict[str, object]] = {name: {} for name in names}
    for view, view_names in names_by_view.items():
        instrument_col = state.duckdb.instrument_columns.get(view)
        datetime_col = state.duckdb.datetime_columns.get(view)
        if not instrument_col or not datetime_col:
            return _error(
                "DuckDB view missing instrument/datetime columns",
                status_code=500,
                details={"view": view},
            )

        select_columns = ", ".join(_quote_ident(name) for name in view_names)
        date_expr = f"CAST({_quote_ident(datetime_col)} AS DATE)"
        query = (
            f"SELECT {date_expr} AS date, {select_columns} "
            f"FROM {_quote_ident(view)} "
            f"WHERE {_quote_ident(instrument_col)} = ? "
            f"AND {date_expr} BETWEEN ? AND ? "
            f"ORDER BY {date_expr}"
        )
        cursor = state.duckdb.conn.execute(query, [ticker, start, end])
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()

        for row in rows:
            record = dict(zip(columns, row))
            date_value = _normalize_date(record["date"])
            for name in view_names:
                values_by_feature[name][date_value] = _normalize_value(record[name])

    features_payload: dict[str, list[dict[str, object]]] = {}
    missing_ratio: dict[str, float] = {}
    sources: dict[str, str] = {}
    total_dates = len(calendar_dates)
    missing_dates: list[str] = []

    per_feature_series: dict[str, list[dict[str, object]]] = {}
    per_feature_missing: dict[str, int] = {}
    for name in names:
        series: list[dict[str, object]] = []
        missing_count = 0
        values = values_by_feature.get(name, {})
        for day in calendar_dates:
            value = values.get(day)
            normalized = _normalize_value(value)
            if _is_missing(normalized):
                missing_count += 1
                normalized = None
            series.append({"date": day, "value": normalized})
        per_feature_series[name] = series
        per_feature_missing[name] = missing_count

    for day_index, day in enumerate(calendar_dates):
        if all(
            _is_missing(per_feature_series[name][day_index]["value"])
            for name in names
        ):
            missing_dates.append(day)

    for name in names:
        features_payload[name] = per_feature_series[name]
        missing_ratio[name] = (
            per_feature_missing[name] / total_dates if total_dates else 0.0
        )
        sources[name] = state.duckdb.feature_sources[name]

    return JSONResponse(
        {
            "ticker": ticker,
            "from": start,
            "to": end,
            "features": features_payload,
            "meta": {
                "missing_ratio": missing_ratio,
                "sources": sources,
                "missing_dates": missing_dates,
            },
        }
    )


async def feature_settings(request: Request) -> JSONResponse:
    state = request.app.state
    if not hasattr(state, "feature_settings_path"):
        state.feature_settings_path = FEATURE_SETTINGS_PATH
    if not hasattr(state, "feature_settings"):
        state.feature_settings = _load_feature_settings(state.feature_settings_path)
    if request.method == "GET":
        return JSONResponse({"features": state.feature_settings})

    try:
        payload = await request.json()
    except ValueError:
        return _error("Invalid JSON payload")

    settings = _coerce_feature_settings(payload)
    state.feature_settings = settings
    _save_feature_settings(state.feature_settings_path, settings)
    return JSONResponse({"features": state.feature_settings})


async def indexes(request: Request) -> JSONResponse:
    state = request.app.state
    return JSONResponse({"count": len(state.index_list), "indexes": state.index_list})


async def instrument_meta(request: Request) -> JSONResponse:
    state = request.app.state
    raw_ticker = request.query_params.get("ticker")
    if not raw_ticker:
        return _error("ticker is required")
    ticker = raw_ticker.strip().lower()
    if not ticker:
        return _error("ticker is required")

    meta = state.instrument_meta.get(ticker)
    if not meta:
        return JSONResponse({"ticker": ticker, "sector": "", "industry": ""})

    sector = meta.get("sector", "")
    payload = {"ticker": ticker, "sector": sector, "industry": meta.get("industry", "")}
    return JSONResponse(payload)


async def index_series(request: Request) -> JSONResponse:
    state = request.app.state
    raw_instrument = request.query_params.get("instrument")
    if not raw_instrument:
        return _error("instrument is required")
    instrument = raw_instrument.strip().lower()
    if not instrument:
        return _error("instrument is required")
    if instrument not in state.instrument_set:
        return _error("Unknown instrument", details={"ticker": raw_instrument})

    names_param = request.query_params.get("names")
    if not names_param:
        return _error("names is required when requesting index data")
    names = [name.strip() for name in names_param.split(",") if name.strip()]
    if not names:
        return _error("names is required when requesting index data")

    try:
        start = _parse_iso_date(request.query_params.get("from"), "from")
        end = _parse_iso_date(request.query_params.get("to"), "to")
        calendar_requested = slice_calendar(
            state.calendar_dates, state.calendar_index, start, end
        )
    except (ValueError, KeyError) as exc:
        return _error(str(exc))

    missing_names = [name for name in names if name not in state.index_defs]
    if missing_names:
        return _error("Unknown index names", details={"missing": missing_names})

    index_payload: dict[str, list[dict[str, object]]] = {}
    for name in names:
        definition = state.index_defs[name]
        kind = definition.get("kind")
        series: list[dict[str, object]] = []

        if kind == "market":
            index_ticker = definition["ticker"]
            try:
                index_closes = _load_close_series(index_ticker, start, end)
            except RuntimeError as exc:
                return _error(str(exc), status_code=500)

            for day in calendar_requested:
                close = index_closes.get(day)
                series.append({"date": day, "value": close})

        else:
            return _error("Unknown index kind", details={"name": name})

        index_payload[name] = series

    return JSONResponse(
        {
            "instrument": instrument,
            "from": start,
            "to": end,
            "indexes": index_payload,
        }
    )


async def feature_power(request: Request) -> JSONResponse:
    state = request.app.state
    try:
        payload = await request.json()
    except ValueError:
        return _error("Invalid JSON payload")

    universe = payload.get("universe", "all")
    target = payload.get("target", "ret_cc")
    method = (payload.get("method") or "spearman").lower()
    horizon_days = payload.get("horizon_days", 1)
    features = payload.get("features", [])

    if method not in {"spearman", "pearson"}:
        return _error("method must be spearman or pearson")
    try:
        horizon_days = int(horizon_days)
    except (TypeError, ValueError):
        return _error("horizon_days must be an integer")
    if horizon_days < 0:
        return _error("horizon_days must be non-negative")

    try:
        date_from = _parse_iso_date(payload.get("date_from"), "date_from")
        date_to = _parse_iso_date(payload.get("date_to"), "date_to")
    except ValueError as exc:
        return _error(str(exc))

    if not isinstance(features, list) or not features:
        return _error("features must be a non-empty list")

    universe_list: list[str] = []
    if isinstance(universe, list):
        universe_list = [str(item).strip().lower() for item in universe if str(item).strip()]
    elif isinstance(universe, str):
        universe_key = universe.strip().lower()
        if universe_key in {"all", "equity", "instruments"}:
            universe_list = [item["ticker"] for item in state.instruments_all]
        elif universe_key in {"indexes", "index"}:
            universe_list = [item["ticker"] for item in state.instruments_indexes]
        else:
            universe_list = [
                name.strip().lower()
                for name in universe_key.split(",")
                if name.strip()
            ]
    else:
        return _error("universe must be a string or list")

    if not universe_list:
        return _error("universe resolved to an empty list")

    features = [str(name).strip() for name in features if str(name).strip()]
    if not features:
        return _error("features must be a non-empty list")

    missing_features = [
        name for name in features if name not in state.duckdb.feature_sources
    ]
    if missing_features:
        return _error("Unknown feature names", details={"missing": missing_features})

    try:
        target_map, valid_dates = _build_target_map(
            universe_list,
            date_from,
            date_to,
            horizon_days,
            target,
            state.calendar_dates,
            state.calendar_index,
        )
    except RuntimeError as exc:
        return _error(str(exc), status_code=500)
    except ValueError as exc:
        return _error(str(exc))

    results: list[dict] = []
    for feature_name in features:
        view = state.duckdb.feature_sources[feature_name]
        instrument_col = state.duckdb.instrument_columns.get(view)
        datetime_col = state.duckdb.datetime_columns.get(view)
        if not instrument_col or not datetime_col:
            return _error(
                "DuckDB view missing instrument/datetime columns",
                status_code=500,
                details={"view": view},
            )

        date_expr = f"CAST({_quote_ident(datetime_col)} AS DATE)"
        placeholders = ", ".join(["?"] * len(universe_list))
        query = (
            f"SELECT {_quote_ident(instrument_col)} AS instrument, "
            f"{date_expr} AS date, {_quote_ident(feature_name)} AS value "
            f"FROM {_quote_ident(view)} "
            f"WHERE {_quote_ident(instrument_col)} IN ({placeholders}) "
            f"AND {date_expr} BETWEEN ? AND ? "
            f"ORDER BY {date_expr}"
        )
        rows = state.duckdb.conn.execute(
            query, universe_list + [date_from, date_to]
        ).fetchall()

        date_pairs: dict[str, list[tuple[float, float]]] = {}
        n_obs = 0
        for instrument, date_value, value in rows:
            date_text = _normalize_date(date_value)
            targets = target_map.get(date_text)
            if not targets:
                continue
            target_value = targets.get(str(instrument).lower())
            if target_value is None:
                continue
            normalized = _normalize_value(value)
            if _is_missing(normalized):
                continue
            date_pairs.setdefault(date_text, []).append(
                (float(normalized), float(target_value))
            )

        ic_ts: list[dict[str, object]] = []
        ic_values: list[float] = []
        decile_sum = [0.0] * 10
        decile_count = [0] * 10

        for day in valid_dates:
            pairs = date_pairs.get(day)
            if not pairs:
                continue
            values_x = [pair[0] for pair in pairs]
            values_y = [pair[1] for pair in pairs]
            if method == "spearman":
                ic = _spearman_corr(values_x, values_y)
            else:
                ic = _pearson_corr(values_x, values_y)
            if ic is not None:
                ic_values.append(ic)
                ic_ts.append({"date": day, "ic": ic})

            deciles = _decile_means(pairs)
            if deciles:
                for idx, mean in enumerate(deciles):
                    if mean is None:
                        continue
                    decile_sum[idx] += mean
                    decile_count[idx] += 1

            n_obs += len(pairs)

        ic_mean = sum(ic_values) / len(ic_values) if ic_values else None
        ic_std = None
        ic_ir = None
        t_stat = None
        if ic_values and len(ic_values) > 1:
            mean = ic_mean or 0.0
            var = sum((value - mean) ** 2 for value in ic_values) / (len(ic_values) - 1)
            ic_std = math.sqrt(var)
            if ic_std:
                ic_ir = mean / ic_std
                t_stat = mean / (ic_std / math.sqrt(len(ic_values)))

        decile_curve: list[Optional[float]] = []
        for idx in range(10):
            if decile_count[idx]:
                decile_curve.append(decile_sum[idx] / decile_count[idx])
            else:
                decile_curve.append(None)

        decile_spread = None
        if decile_curve[0] is not None and decile_curve[-1] is not None:
            decile_spread = decile_curve[-1] - decile_curve[0]

        results.append(
            {
                "feature": feature_name,
                "n_obs": n_obs,
                "ic_mean": ic_mean,
                "ic_std": ic_std,
                "ic_ir": ic_ir,
                "t_stat": t_stat,
                "decile_spread": decile_spread,
                "decile_curve": decile_curve,
                "ic_ts": ic_ts,
            }
        )

    return JSONResponse(
        {
            "count": len(results),
            "params": {
                "universe": universe,
                "target": target,
                "horizon_days": horizon_days,
                "date_from": date_from,
                "date_to": date_to,
                "method": method,
                "neutralize": payload.get("neutralize"),
                "regimes": payload.get("regimes"),
            },
            "results": results,
        }
    )


async def feature_power_summary(request: Request) -> JSONResponse:
    state = request.app.state
    try:
        payload = await request.json()
    except ValueError:
        return _error("Invalid JSON payload")

    universe = payload.get("universe", "all")
    target = payload.get("target", "ret_cc")
    method = (payload.get("method") or "spearman").lower()
    horizon_days = payload.get("horizon_days", 1)
    features = payload.get("features")

    if method not in {"spearman", "pearson"}:
        return _error("method must be spearman or pearson")
    try:
        horizon_days = int(horizon_days)
    except (TypeError, ValueError):
        return _error("horizon_days must be an integer")
    if horizon_days < 0:
        return _error("horizon_days must be non-negative")

    try:
        date_from = _parse_iso_date(payload.get("date_from"), "date_from")
        date_to = _parse_iso_date(payload.get("date_to"), "date_to")
    except ValueError as exc:
        return _error(str(exc))

    try:
        universe_list = _resolve_universe(state, universe)
    except ValueError as exc:
        return _error(str(exc))
    if not universe_list:
        return _error("universe resolved to an empty list")

    if features is None:
        features = sorted(state.duckdb.feature_sources)
    elif not isinstance(features, list):
        return _error("features must be a list")
    else:
        features = [str(name).strip() for name in features if str(name).strip()]

    if not features:
        return _error("features must be a non-empty list")

    missing_features = [
        name for name in features if name not in state.duckdb.feature_sources
    ]
    if missing_features:
        return _error("Unknown feature names", details={"missing": missing_features})

    try:
        target_map, valid_dates = _build_target_map(
            universe_list,
            date_from,
            date_to,
            horizon_days,
            target,
            state.calendar_dates,
            state.calendar_index,
        )
    except RuntimeError as exc:
        return _error(str(exc), status_code=500)
    except ValueError as exc:
        return _error(str(exc))

    results: list[dict] = []
    for feature_name in features:
        view = state.duckdb.feature_sources[feature_name]
        instrument_col = state.duckdb.instrument_columns.get(view)
        datetime_col = state.duckdb.datetime_columns.get(view)
        if not instrument_col or not datetime_col:
            return _error(
                "DuckDB view missing instrument/datetime columns",
                status_code=500,
                details={"view": view},
            )

        date_expr = f"CAST({_quote_ident(datetime_col)} AS DATE)"
        placeholders = ", ".join(["?"] * len(universe_list))
        query = (
            f"SELECT {_quote_ident(instrument_col)} AS instrument, "
            f"{date_expr} AS date, {_quote_ident(feature_name)} AS value "
            f"FROM {_quote_ident(view)} "
            f"WHERE {_quote_ident(instrument_col)} IN ({placeholders}) "
            f"AND {date_expr} BETWEEN ? AND ? "
            f"ORDER BY {date_expr}"
        )
        rows = state.duckdb.conn.execute(
            query, universe_list + [date_from, date_to]
        ).fetchall()

        date_pairs: dict[str, list[tuple[float, float]]] = {}
        n_obs = 0
        for instrument, date_value, value in rows:
            date_text = _normalize_date(date_value)
            targets = target_map.get(date_text)
            if not targets:
                continue
            target_value = targets.get(str(instrument).lower())
            if target_value is None:
                continue
            normalized = _normalize_value(value)
            if _is_missing(normalized):
                continue
            date_pairs.setdefault(date_text, []).append(
                (float(normalized), float(target_value))
            )

        ic_values: list[float] = []
        decile_sum = [0.0] * 10
        decile_count = [0] * 10

        for day in valid_dates:
            pairs = date_pairs.get(day)
            if not pairs:
                continue
            values_x = [pair[0] for pair in pairs]
            values_y = [pair[1] for pair in pairs]
            if method == "spearman":
                ic = _spearman_corr(values_x, values_y)
            else:
                ic = _pearson_corr(values_x, values_y)
            if ic is not None:
                ic_values.append(ic)

            deciles = _decile_means(pairs)
            if deciles:
                for idx, mean in enumerate(deciles):
                    if mean is None:
                        continue
                    decile_sum[idx] += mean
                    decile_count[idx] += 1

            n_obs += len(pairs)

        ic_mean = sum(ic_values) / len(ic_values) if ic_values else None
        ic_std = None
        ic_ir = None
        t_stat = None
        if ic_values and len(ic_values) > 1:
            mean = ic_mean or 0.0
            var = sum((value - mean) ** 2 for value in ic_values) / (len(ic_values) - 1)
            ic_std = math.sqrt(var)
            if ic_std:
                ic_ir = mean / ic_std
                t_stat = mean / (ic_std / math.sqrt(len(ic_values)))

        decile_spread = None
        if decile_count[0] and decile_count[-1]:
            low = decile_sum[0] / decile_count[0]
            high = decile_sum[-1] / decile_count[-1]
            decile_spread = high - low

        results.append(
            {
                "feature": feature_name,
                "n_obs": n_obs,
                "ic_mean": ic_mean,
                "ic_std": ic_std,
                "ic_ir": ic_ir,
                "t_stat": t_stat,
                "decile_spread": decile_spread,
            }
        )

    return JSONResponse(
        {
            "count": len(results),
            "params": {
                "universe": universe,
                "target": target,
                "horizon_days": horizon_days,
                "date_from": date_from,
                "date_to": date_to,
                "method": method,
                "neutralize": payload.get("neutralize"),
                "regimes": payload.get("regimes"),
            },
            "results": results,
        }
    )


async def feature_power_detail(request: Request) -> JSONResponse:
    state = request.app.state
    try:
        payload = await request.json()
    except ValueError:
        return _error("Invalid JSON payload")

    universe = payload.get("universe", "all")
    target = payload.get("target", "ret_cc")
    method = (payload.get("method") or "spearman").lower()
    horizon_days = payload.get("horizon_days", 1)
    feature_name = payload.get("feature")
    rolling_window = payload.get("rolling_window", 20)

    if method not in {"spearman", "pearson"}:
        return _error("method must be spearman or pearson")
    try:
        horizon_days = int(horizon_days)
    except (TypeError, ValueError):
        return _error("horizon_days must be an integer")
    if horizon_days < 0:
        return _error("horizon_days must be non-negative")
    try:
        rolling_window = int(rolling_window)
    except (TypeError, ValueError):
        return _error("rolling_window must be an integer")
    if rolling_window <= 0:
        return _error("rolling_window must be a positive integer")

    if not isinstance(feature_name, str) or not feature_name.strip():
        return _error("feature is required")
    feature_name = feature_name.strip()

    try:
        date_from = _parse_iso_date(payload.get("date_from"), "date_from")
        date_to = _parse_iso_date(payload.get("date_to"), "date_to")
    except ValueError as exc:
        return _error(str(exc))

    try:
        universe_list = _resolve_universe(state, universe)
    except ValueError as exc:
        return _error(str(exc))
    if not universe_list:
        return _error("universe resolved to an empty list")

    if feature_name not in state.duckdb.feature_sources:
        return _error("Unknown feature name", details={"missing": [feature_name]})

    try:
        target_map, valid_dates = _build_target_map(
            universe_list,
            date_from,
            date_to,
            horizon_days,
            target,
            state.calendar_dates,
            state.calendar_index,
        )
    except RuntimeError as exc:
        return _error(str(exc), status_code=500)
    except ValueError as exc:
        return _error(str(exc))

    view = state.duckdb.feature_sources[feature_name]
    instrument_col = state.duckdb.instrument_columns.get(view)
    datetime_col = state.duckdb.datetime_columns.get(view)
    if not instrument_col or not datetime_col:
        return _error(
            "DuckDB view missing instrument/datetime columns",
            status_code=500,
            details={"view": view},
        )

    date_expr = f"CAST({_quote_ident(datetime_col)} AS DATE)"
    placeholders = ", ".join(["?"] * len(universe_list))
    query = (
        f"SELECT {_quote_ident(instrument_col)} AS instrument, "
        f"{date_expr} AS date, {_quote_ident(feature_name)} AS value "
        f"FROM {_quote_ident(view)} "
        f"WHERE {_quote_ident(instrument_col)} IN ({placeholders}) "
        f"AND {date_expr} BETWEEN ? AND ? "
        f"ORDER BY {date_expr}"
    )
    rows = state.duckdb.conn.execute(
        query, universe_list + [date_from, date_to]
    ).fetchall()

    date_pairs: dict[str, list[tuple[float, float]]] = {}
    for instrument, date_value, value in rows:
        date_text = _normalize_date(date_value)
        targets = target_map.get(date_text)
        if not targets:
            continue
        target_value = targets.get(str(instrument).lower())
        if target_value is None:
            continue
        normalized = _normalize_value(value)
        if _is_missing(normalized):
            continue
        date_pairs.setdefault(date_text, []).append(
            (float(normalized), float(target_value))
        )

    daily_ic: list[dict[str, object]] = []
    daily_decile_spread: list[dict[str, object]] = []
    daily_n_obs: list[dict[str, object]] = []
    ic_values: list[Optional[float]] = []

    for day in valid_dates:
        pairs = date_pairs.get(day)
        if not pairs:
            daily_ic.append({"date": day, "value": None})
            daily_decile_spread.append({"date": day, "value": None})
            daily_n_obs.append({"date": day, "value": 0})
            ic_values.append(None)
            continue

        values_x = [pair[0] for pair in pairs]
        values_y = [pair[1] for pair in pairs]
        if method == "spearman":
            ic = _spearman_corr(values_x, values_y)
        else:
            ic = _pearson_corr(values_x, values_y)
        daily_ic.append({"date": day, "value": ic})
        ic_values.append(ic)

        deciles = _decile_means(pairs)
        spread = None
        if deciles and deciles[0] is not None and deciles[-1] is not None:
            spread = deciles[-1] - deciles[0]
        daily_decile_spread.append({"date": day, "value": spread})
        daily_n_obs.append({"date": day, "value": len(pairs)})

    rolling = _rolling_metrics(valid_dates, ic_values, rolling_window)

    return JSONResponse(
        {
            "feature": feature_name,
            "params": {
                "universe": universe,
                "target": target,
                "horizon_days": horizon_days,
                "date_from": date_from,
                "date_to": date_to,
                "method": method,
                "rolling_window": rolling_window,
                "neutralize": payload.get("neutralize"),
                "regimes": payload.get("regimes"),
            },
            "daily": {
                "ic": daily_ic,
                "decile_spread": daily_decile_spread,
                "n_obs": daily_n_obs,
            },
            "rolling": rolling,
        }
    )


def create_app() -> Starlette:
    app = Starlette(
        debug=False,
        routes=[
            Route("/", homepage),
            Route("/feature-power", feature_power_page),
            Route("/health", health),
            Route("/tickers", tickers),
            Route("/bars", bars),
            Route("/features", features),
            Route("/feature-settings", feature_settings, methods=["GET", "POST"]),
            Route("/indexes", indexes),
            Route("/instrument-meta", instrument_meta),
            Route("/index-series", index_series),
            Route("/feature_power", feature_power, methods=["POST"]),
            Route("/feature_power_summary", feature_power_summary, methods=["POST"]),
            Route("/feature_power_detail", feature_power_detail, methods=["POST"]),
        ],
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.feature_settings_path = FEATURE_SETTINGS_PATH
    app.state.feature_settings = _load_feature_settings(FEATURE_SETTINGS_PATH)
    app.state.index_list = []
    app.state.index_defs = {}
    app.state.instrument_meta = {}

    @app.on_event("startup")
    async def startup() -> None:
        paths = load_paths()
        missing_required, missing_optional = validate_paths(paths)
        if missing_required:
            raise RuntimeError(f"Missing required paths: {', '.join(missing_required)}")

        feature_settings = _load_feature_settings(FEATURE_SETTINGS_PATH)
        duckdb_state = init_duckdb(paths)
        init_qlib(paths.qlib_provider_uri)

        calendar_dates = load_calendar(paths.calendar)
        calendar_index = build_calendar_index(calendar_dates)

        app.state.paths = paths
        app.state.duckdb = duckdb_state
        app.state.missing_required_paths = missing_required
        app.state.missing_optional_paths = missing_optional
        app.state.feature_settings_path = FEATURE_SETTINGS_PATH
        app.state.feature_settings = feature_settings
        app.state.instruments_all = load_instruments(paths.instruments_all, "equity")
        app.state.instruments_indexes = load_instruments(paths.instruments_indexes, "index")
        app.state.instrument_set = {item["ticker"] for item in app.state.instruments_all}
        app.state.index_set = {item["ticker"] for item in app.state.instruments_indexes}
        app.state.ticker_set = app.state.instrument_set
        app.state.instrument_bounds = {}
        for item in app.state.instruments_all:
            app.state.instrument_bounds[item["ticker"]] = (
                _parse_optional_date(item.get("start")),
                _parse_optional_date(item.get("end")),
            )
        app.state.index_bounds = {}
        for item in app.state.instruments_indexes:
            app.state.index_bounds[item["ticker"]] = (
                _parse_optional_date(item.get("start")),
                _parse_optional_date(item.get("end")),
            )
        instrument_meta, sector_to_tickers, sector_bounds, sector_representative = (
            _load_sector_map(paths.sector_map, duckdb_state.conn)
        )
        app.state.instrument_meta = instrument_meta
        app.state.sector_to_tickers = sector_to_tickers
        app.state.sector_bounds = sector_bounds
        app.state.sector_representative = sector_representative
        index_list, index_defs = _build_index_definitions(app.state.instruments_indexes)
        app.state.index_list = index_list
        app.state.index_defs = index_defs
        app.state.calendar_dates = calendar_dates
        app.state.calendar_index = calendar_index
        app.state.qlib_initialized = True

    return app


app = create_app()
