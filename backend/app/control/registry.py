"""Registry of whitelisted quant core commands runnable via the UI control API.

Each task defines:
  - id: stable identifier used in API paths
  - summary: human-readable description
  - params: ordered schema list (name, type, required, default, description)
  - build(argv_params) -> list[str]: constructs the subprocess argv (python -m ... style)

We restrict commands to a safe subset; NO arbitrary shell execution.
Future: add permission scopes, rate limits, concurrency caps.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any, List, Dict
import shlex
import os
from pathlib import Path


@dataclass
class ParamSpec:
    name: str
    type: str = "str"
    required: bool = False
    default: Any | None = None
    description: str | None = None
    dev_only: bool = False


@dataclass
class TaskDef:
    id: str
    summary: str
    module: str  # python -m <module>
    params: List[ParamSpec]
    build: Callable[[Dict[str, Any]], List[str]]
    category: str = "general"
    use_core_root_cwd: bool = False  # if True, subprocess cwd = QUANT_CORE_ROOT


_REGISTRY: Dict[str, TaskDef] = {}


def register(task: TaskDef) -> None:
    if task.id in _REGISTRY:
        raise ValueError(f"Duplicate task id: {task.id}")
    _REGISTRY[task.id] = task


def list_tasks() -> List[TaskDef]:
    return list(_REGISTRY.values())


def get_task(task_id: str) -> TaskDef | None:
    return _REGISTRY.get(task_id)


# ------------------------- Builders ---------------------------------------


def _export_artifacts_builder(p: Dict[str, Any]) -> List[str]:
    out_root = p.get("out_root") or "./artifacts_generated"
    args = ["--out-root", out_root]
    if p.get("runs_db"):
        args += ["--runs-db", p["runs_db"]]
    if p.get("min_days") is not None:
        args += ["--min-days", str(p["min_days"])]
    if p.get("limit") is not None:
        args += ["--limit", str(p["limit"])]
    # strict means: treat zero strategies as error (so do NOT pass --allow-empty)
    # non-strict: allow empty export silently
    if not p.get("strict"):
        args.append("--allow-empty")
    if p.get("auto_fallback"):
        args.append("--auto-fallback")
    if p.get("mvp"):
        args.append("--mvp")
    if p.get("synthetic"):
        args.append("--synthetic")
    if p.get("fallback_data"):
        args += ["--fallback-data", p["fallback_data"]]
    if p.get("data"):
        args += ["--data", p["data"]]
    return args


register(
    TaskDef(
        id="export_artifacts",
        summary="Export strategies & equity curves for UI consumption",
        module="scripts.export_ui_artifacts",
        params=[
            ParamSpec(
                "out_root",
                required=False,
                default="./quant_generated",
                description="Output root directory",
            ),
            ParamSpec("runs_db", required=False, description="Path to runs SQLite DB"),
            ParamSpec("min_days", type="int", default=30),
            ParamSpec("limit", type="int", default=50),
            ParamSpec("data", description="Primary raw history CSV for MVP fallback"),
            ParamSpec(
                "fallback_data", description="Secondary CSV used only for auto fallback"
            ),
            ParamSpec(
                "strict",
                type="bool",
                default=False,
                description="Fail if zero strategies exported (ignore synthetic). If false, allows empty export",
            ),
            ParamSpec(
                "synthetic",
                type="bool",
                default=False,
                dev_only=True,
                description="Dev: fabricate placeholder strategies",
            ),
            ParamSpec(
                "auto_fallback",
                type="bool",
                default=False,
                description="If runs export empty, automatically run MVP fallback (uses data or fallback_data)",
            ),
            ParamSpec(
                "mvp",
                type="bool",
                default=False,
                description="Force MVP fallback even if runs DB present",
            ),
        ],
        build=_export_artifacts_builder,
        category="artifacts",
        use_core_root_cwd=True,
    )
)

# ------------------- Phase A Tasks ---------------------------------------


def _backtest_batch_builder(p: Dict[str, Any]) -> List[str]:
    args: List[str] = []
    # minimal required: signal, name_prefix, out
    if p.get("signal"):
        args += ["--signal", p["signal"]]
    if p.get("name_prefix"):
        args += ["--name-prefix", p["name_prefix"]]
    if p.get("out"):
        args += ["--out", p["out"]]
    # optional sweeps (space-separated values => pass as repeated args?) For simplicity pass as is.
    for multi in [
        "modes",
        "long_q",
        "short_q",
        "z_clip",
        "max_weight",
        "gross",
        "rebalance",
        "holding",
    ]:
        key_cli = multi.replace("_", "-")
        if multi in p and p[multi]:
            vals = p[multi] if isinstance(p[multi], list) else [p[multi]]
            args += [f"--{key_cli}", *[str(v) for v in vals]]
    if p.get("universe_min") is not None:
        args += ["--universe-min", str(p["universe_min"])]
    return args


register(
    TaskDef(
        id="backtest_batch",
        summary="Generate parameter sweep strategy configs",
        module="src.cli.strategies_sweep",
        params=[
            ParamSpec("signal", required=True, description="Signal parquet path"),
            ParamSpec("name_prefix", required=True, description="Strategy name prefix"),
            ParamSpec("out", required=True, description="Output strategies JSON path"),
            ParamSpec(
                "modes", description="Modes (space separated)", default=["long_short"]
            ),
            ParamSpec("long_q", description="Long quantiles", default=[0.2]),
            ParamSpec("short_q", description="Short quantiles", default=[0.2]),
            ParamSpec("z_clip", description="Z-score clips", default=[3.0]),
            ParamSpec("max_weight", description="Max weights", default=[0.05]),
            ParamSpec("gross", description="Gross leverage options", default=[1.0]),
            ParamSpec("rebalance", description="Rebalance freqs", default=["D"]),
            ParamSpec("holding", description="Holding periods", default=[1]),
            ParamSpec("universe_min", type="int", default=30),
        ],
        build=_backtest_batch_builder,
        category="backtest",
        use_core_root_cwd=True,
    )
)


def _select_strategies_builder(p: Dict[str, Any]) -> List[str]:
    args: List[str] = []
    if p.get("strategies"):
        args += ["--strategies", p["strategies"]]
    if p.get("returns"):
        args += ["--returns", p["returns"]]
    if p.get("walk_forward"):
        args += ["--walk-forward", p["walk_forward"]]
    if p.get("top") is not None:
        args += ["--top", str(p["top"])]
    if p.get("out_prefix"):
        args += ["--out-prefix", p["out_prefix"]]
    if p.get("primary"):
        args += ["--primary", p["primary"]]
    if p.get("secondary"):
        args += ["--secondary", p["secondary"]]
    return args


register(
    TaskDef(
        id="select_strategies",
        summary="Evaluate & rank strategies (persist summary + weight panels)",
        module="src.cli.strategies_select",
        params=[
            ParamSpec(
                "strategies",
                required=True,
                description="Strategy settings JSON produced by sweep",
            ),
            ParamSpec(
                "returns", required=True, description="Returns panel (parquet/csv)"
            ),
            ParamSpec("walk_forward", description="Walk-forward JSON config"),
            ParamSpec("top", type="int", default=5),
            ParamSpec("out_prefix", default="strategies_eval"),
            ParamSpec("primary", default="sharpe"),
            ParamSpec("secondary", default="cagr"),
        ],
        build=_select_strategies_builder,
        category="backtest",
        use_core_root_cwd=True,
    )
)


def _build_manifest_builder(p: Dict[str, Any]) -> List[str]:
    # Typer exposes 'build' as the default command entrypoint when invoked via python -m app.cli.build_manifest build
    # We call the module without the subcommand to match the error observed; removing 'build' fixes unexpected extra argument.
    args: List[str] = []
    if p.get("artifacts"):
        args += ["--artifacts", p["artifacts"]]
    if p.get("git"):
        args += ["--git", p["git"]]
    if p.get("data_version"):
        args += ["--data-version", p["data_version"]]
    return args


register(
    TaskDef(
        id="build_manifest",
        summary="Generate / refresh artifacts manifest.json",
        module="app.cli.build_manifest",
        params=[
            ParamSpec("artifacts", default="artifacts", description="Artifacts root"),
            ParamSpec("git", description="Git commit short hash"),
            ParamSpec("data_version", description="Data version string"),
        ],
        build=_build_manifest_builder,
        category="publish",
        use_core_root_cwd=False,  # runs in UI backend environment
    )
)


def _daily_pipeline_builder(p: Dict[str, Any]) -> List[str]:
    args: List[str] = []
    if p.get("signal"):
        args += ["--signal", p["signal"]]
    if p.get("name_prefix"):
        args += ["--name-prefix", p["name_prefix"]]
    if p.get("strategies_out"):
        args += ["--strategies-out", p["strategies_out"]]
    if p.get("skip_sweep"):
        args.append("--skip-sweep")
    if p.get("returns"):
        args += ["--returns", p["returns"]]
    if p.get("runs_db"):
        args += ["--runs-db", p["runs_db"]]
    if p.get("export_out"):
        args += ["--export-out", p["export_out"]]
    if p.get("top") is not None:
        args += ["--top", str(p["top"])]
    if p.get("min_days") is not None:
        args += ["--min-days", str(p["min_days"])]
    if p.get("limit") is not None:
        args += ["--limit", str(p["limit"])]
    if p.get("strict"):
        args.append("--strict")
    if p.get("manifest"):
        args.append("--manifest")
    if p.get("ui_backend"):
        args += ["--ui-backend", p["ui_backend"]]
    # Fallback export flags propagated to export_ui_artifacts
    if p.get("data"):
        args += ["--data", p["data"]]
    if p.get("fallback_data"):
        args += ["--fallback-data", p["fallback_data"]]
    if p.get("auto_fallback"):
        args.append("--auto-fallback")
    if p.get("mvp"):
        args.append("--mvp")
    if p.get("synthetic"):
        args.append("--synthetic")
    return args


register(
    TaskDef(
        id="daily_pipeline",
        summary="Run minimal daily chain (sweep->select->export->manifest)",
        module="scripts.daily_pipeline",
        params=[
            ParamSpec(
                "signal", description="Signal parquet path (omit with skip_sweep)"
            ),
            ParamSpec("name_prefix", default="daily"),
            ParamSpec("strategies_out", default="configs/strategies_sweep.json"),
            ParamSpec("skip_sweep", type="bool", default=False),
            ParamSpec("returns", description="Returns panel", required=True),
            ParamSpec("runs_db", default="runs.sqlite"),
            ParamSpec("export_out", default="artifacts_publish"),
            ParamSpec("top", type="int", default=5),
            ParamSpec("min_days", type="int", default=30),
            ParamSpec("limit", type="int", default=100),
            ParamSpec("strict", type="bool", default=False),
            ParamSpec("manifest", type="bool", default=False),
            ParamSpec("ui_backend", description="UI backend path for manifest"),
            ParamSpec("data", description="Primary raw history CSV for MVP fallback"),
            ParamSpec(
                "fallback_data", description="Secondary CSV used only for auto fallback"
            ),
            ParamSpec(
                "auto_fallback",
                type="bool",
                default=False,
                description="If export has zero runs, attempt MVP fallback automatically",
            ),
            ParamSpec(
                "mvp",
                type="bool",
                default=False,
                description="Force MVP fallback regardless of runs DB contents",
            ),
            ParamSpec(
                "synthetic",
                type="bool",
                default=False,
                dev_only=True,
                description="Dev: fabricate placeholder strategies if all else empty",
            ),
        ],
        build=_daily_pipeline_builder,
        category="pipeline",
        use_core_root_cwd=True,
    )
)

# Additional tasks can be appended here with new register() calls.

# ------------------- Data Curation Tasks ---------------------------------


def _build_curated_all_builder(p: Dict[str, Any]) -> List[str]:
    args: List[str] = []
    if p.get("borsdata_csv"):
        args += ["--borsdata-csv", p["borsdata_csv"]]
    if p.get("stock_history_csv"):
        args += ["--stock-history-csv", p["stock_history_csv"]]
    if p.get("eursek_csv"):
        args += ["--eursek-csv", p["eursek_csv"]]
    if p.get("universe_csv"):
        args += ["--universe-csv", p["universe_csv"]]
    if p.get("exogener"):
        # pass list
        exo = p["exogener"] if isinstance(p["exogener"], list) else [p["exogener"]]
        args += ["--exogener", *exo]
    if p.get("data_version"):
        args += ["--data-version", p["data_version"]]
    if p.get("skip_calendar"):
        args.append("--skip-calendar")
    if p.get("skip_exogener"):
        args.append("--skip-exogener")
    if p.get("skip_fx"):
        args.append("--skip-fx")
    if p.get("skip_costs"):
        args.append("--skip-costs")
    if p.get("calendar_start"):
        args += ["--calendar-start", p["calendar_start"]]
    if p.get("calendar_end"):
        args += ["--calendar-end", p["calendar_end"]]
    if p.get("dry_run"):
        args.append("--dry-run")
    return args


register(
    TaskDef(
        id="build_curated_all",
        summary="Run full curated data build (bars, calendar, universe, FX, costs, exogenous)",
        module="src.data.build_all",
        params=[
            ParamSpec("borsdata_csv", description="Börsdata history CSV"),
            ParamSpec(
                "stock_history_csv", description="Canonical stock_history OHLCV CSV"
            ),
            ParamSpec("eursek_csv", description="EUR/SEK FX CSV"),
            ParamSpec("universe_csv", description="Universe membership input CSV"),
            ParamSpec(
                "exogener",
                description="Exogenous series list (space separated)",
                default=["DAX", "V2X", "Brent"],
            ),
            ParamSpec("data_version", description="Override data version stamp"),
            ParamSpec("calendar_start", description="Calendar start YYYY-MM-DD"),
            ParamSpec("calendar_end", description="Calendar end YYYY-MM-DD"),
            ParamSpec("skip_calendar", type="bool", default=False),
            ParamSpec("skip_exogener", type="bool", default=False),
            ParamSpec("skip_fx", type="bool", default=False),
            ParamSpec("skip_costs", type="bool", default=False),
            ParamSpec("dry_run", type="bool", default=False),
        ],
        build=_build_curated_all_builder,
        category="data",
        use_core_root_cwd=True,
    )
)


def _refresh_views_builder(p: Dict[str, Any]) -> List[str]:
    # If gen_views has its own CLI flags, add mapping here later.
    return []


register(
    TaskDef(
        id="refresh_views",
        summary="Regenerate DuckDB views / training view",
        module="src.data.gen_views",
        params=[],
        build=_refresh_views_builder,
        category="data",
        use_core_root_cwd=True,
    )
)
