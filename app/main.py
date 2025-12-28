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
    sector_bounds: dict[str, dict[str, str]],
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

    for sector in sorted(sector_bounds.keys()):
        bounds = sector_bounds.get(sector, {})
        entry = {
            "id": f"sector:{sector}",
            "label": sector,
            "kind": "sector",
            "start": bounds.get("start") or "",
            "end": bounds.get("end") or "",
            "sector": sector,
        }
        index_list.append(entry)
        index_defs[entry["id"]] = {"kind": "sector", "sector": sector}

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


def _load_sector_returns(
    conn,
    view: str,
    instrument_col: str,
    datetime_col: str,
    ticker: str,
    start: str,
    end: str,
) -> dict[str, float]:
    date_expr = f"CAST({_quote_ident(datetime_col)} AS DATE)"
    query = (
        f"SELECT {date_expr} AS date, sector_ret "
        f"FROM {_quote_ident(view)} "
        f"WHERE {_quote_ident(instrument_col)} = ? "
        f"AND {date_expr} BETWEEN ? AND ? "
        f"ORDER BY {date_expr}"
    )
    rows = conn.execute(query, [ticker, start, end]).fetchall()
    series: dict[str, float] = {}
    for date_value, ret_value in rows:
        date_text = _normalize_date(date_value)
        ret = _normalize_value(ret_value)
        if _is_missing(ret):
            continue
        series[date_text] = ret
    return series


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
    if sector:
        payload["sector_index"] = f"sector:{sector}"
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

    try:
        instrument_closes = _load_close_series(instrument, start, end)
    except RuntimeError as exc:
        return _error(str(exc), status_code=500)

    base_date = _first_available_date(instrument_closes, calendar_requested)
    if not base_date:
        return _error("Instrument base price not found")

    base_close = instrument_closes.get(base_date)
    if base_close is None:
        return _error("Instrument base price not found")

    calendar_full = slice_calendar(
        state.calendar_dates, state.calendar_index, base_date, end
    )

    index_payload: dict[str, list[dict[str, object]]] = {}
    for name in names:
        definition = state.index_defs[name]
        kind = definition.get("kind")
        series: list[dict[str, object]] = []

        if kind == "market":
            index_ticker = definition["ticker"]
            try:
                index_closes = _load_close_series(index_ticker, base_date, end)
            except RuntimeError as exc:
                return _error(str(exc), status_code=500)
            index_base_date = base_date if index_closes.get(base_date) is not None else None
            if index_base_date is None:
                index_base_date = _first_available_date(index_closes, calendar_full)
            index_base = index_closes.get(index_base_date) if index_base_date else None

            for day in calendar_requested:
                if index_base is None or (index_base_date and day < index_base_date):
                    series.append({"date": day, "value": None})
                    continue
                close = index_closes.get(day)
                if close is None or index_base in (None, 0):
                    value = None
                else:
                    value = base_close * (close / index_base)
                series.append({"date": day, "value": value})

        elif kind == "sector":
            sector = definition["sector"]
            representative = state.sector_representative.get(sector)
            if not representative:
                return _error("Sector index representative missing", details={"sector": sector})

            view = "features_sector"
            schema = state.duckdb.view_schema.get(view, {})
            if "sector_ret" not in schema:
                return _error("sector_ret column missing in features_sector view")

            instrument_col = state.duckdb.instrument_columns.get(view)
            datetime_col = state.duckdb.datetime_columns.get(view)
            if not instrument_col or not datetime_col:
                return _error("features_sector view missing instrument/datetime columns")

            returns = _load_sector_returns(
                state.duckdb.conn,
                view,
                instrument_col,
                datetime_col,
                representative,
                base_date,
                end,
            )
            values_by_date: dict[str, Optional[float]] = {}
            factor = 1.0
            for day in calendar_full:
                if day == base_date:
                    values_by_date[day] = factor
                    continue
                ret = returns.get(day)
                if ret is None:
                    values_by_date[day] = None
                    continue
                factor *= 1 + ret
                values_by_date[day] = factor

            for day in calendar_requested:
                factor_value = values_by_date.get(day)
                value = base_close * factor_value if factor_value is not None else None
                series.append({"date": day, "value": value})

        else:
            return _error("Unknown index kind", details={"name": name})

        index_payload[name] = series

    return JSONResponse(
        {
            "instrument": instrument,
            "from": start,
            "to": end,
            "base_date": base_date,
            "indexes": index_payload,
        }
    )


def create_app() -> Starlette:
    app = Starlette(
        debug=False,
        routes=[
            Route("/", homepage),
            Route("/health", health),
            Route("/tickers", tickers),
            Route("/bars", bars),
            Route("/features", features),
            Route("/feature-settings", feature_settings, methods=["GET", "POST"]),
            Route("/indexes", indexes),
            Route("/instrument-meta", instrument_meta),
            Route("/index-series", index_series),
        ],
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.feature_settings_path = FEATURE_SETTINGS_PATH
    app.state.feature_settings = _load_feature_settings(FEATURE_SETTINGS_PATH)
    app.state.index_list = []
    app.state.index_defs = {}
    app.state.instrument_meta = {}
    app.state.sector_representative = {}

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
        index_list, index_defs = _build_index_definitions(
            app.state.instruments_indexes, sector_bounds
        )
        app.state.index_list = index_list
        app.state.index_defs = index_defs
        app.state.calendar_dates = calendar_dates
        app.state.calendar_index = calendar_index
        app.state.qlib_initialized = True

    return app


app = create_app()
