"""Control endpoints to run whitelisted quant core commands via subprocess.

NOTE: This intentionally keeps a narrow surface area. Only approved tasks
from `app.control.registry` are runnable. No arbitrary shell execution.

POST verbs here bypass the global read-only middleware (middleware updated separately).
"""

from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict
from app.control.registry import list_tasks, get_task
from app.core.config import get_settings
from pathlib import Path
import os
from app.control.jobs import get_manager
import json
import sqlite3
from typing import Optional

try:  # optional dependency
    import duckdb  # type: ignore
except Exception:  # pragma: no cover - optional
    duckdb = None  # type: ignore

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore


# Dynamic loader for quant core data registry to avoid hard import dependency at startup.
def _get_registry(curated_path: Path):  # lazy import
    import importlib, sys

    settings = get_settings()
    core_root = settings.quant_core_root
    if core_root and core_root not in sys.path:
        sys.path.insert(0, core_root)
    try:
        mod = importlib.import_module("src.data.registry")
        get_registry = getattr(mod, "get_registry")
        return get_registry(curated_path)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"registry import failed: {e}")


class RegistryError(Exception):  # fallback placeholder if core not available
    pass


router = APIRouter(tags=["control"], prefix="/control")


class TaskParam(BaseModel):
    name: str
    type: str
    required: bool = False
    default: Any | None = None
    description: str | None = None


class TaskInfo(BaseModel):
    id: str
    summary: str
    category: str
    params: list[TaskParam]


class RunRequest(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    task_id: str
    status: str
    created_at: float
    started_at: float | None
    finished_at: float | None
    exit_code: int | None
    error: str | None
    stdout_tail: list[str]
    stderr_tail: list[str]
    pid: int | None


@router.get("/tasks", response_model=list[TaskInfo])
async def list_control_tasks():
    settings = get_settings()
    payload: list[TaskInfo] = []
    for t in list_tasks():
        params = []
        for p in t.params:
            if p.dev_only and not settings.dev_mode:
                continue
            params.append(
                TaskParam(
                    name=p.name,
                    type=p.type,
                    required=p.required,
                    default=p.default,
                    description=p.description,
                )
            )
        payload.append(
            TaskInfo(
                id=t.id,
                summary=t.summary,
                category=t.category,
                params=params,
            )
        )
    return payload


@router.post("/tasks/{task_id}/run", response_model=JobResponse, status_code=201)
async def run_task(task_id: str, req: RunRequest):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Unknown task id")
    # Basic required param validation
    missing = [p.name for p in task.params if p.required and p.name not in req.params]
    if missing:
        raise HTTPException(status_code=422, detail={"missing": missing})
    args = task.build(req.params)
    mgr = get_manager()
    settings = get_settings()
    cwd = settings.quant_core_root if task.use_core_root_cwd else None
    rec = mgr.run(task.id, task.module, args, cwd=cwd)
    return JobResponse(**rec.to_public())


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs():
    mgr = get_manager()
    return [JobResponse(**j) for j in mgr.list()]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def job_detail(job_id: str):
    mgr = get_manager()
    rec = mgr.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**rec.to_public())


class JobLogs(BaseModel):
    stdout: list[str]
    stderr: list[str]
    truncated: bool


@router.get("/jobs/{job_id}/logs", response_model=JobLogs)
async def job_logs(job_id: str):
    mgr = get_manager()
    rec = mgr.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    truncated = False  # job manager already truncates internally if needed
    return JobLogs(stdout=rec.stdout, stderr=rec.stderr, truncated=truncated)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: str):
    mgr = get_manager()
    rec = mgr.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    mgr.cancel(job_id)
    return JobResponse(**rec.to_public())


class ControlMeta(BaseModel):
    dev_mode: bool
    version: str
    git_commit: str | None = None
    data_version: str | None = None
    quant_core_root: str | None = None
    artifacts_root: str | None = None


@router.get("/meta", response_model=ControlMeta)
async def control_meta():
    settings = get_settings()
    return ControlMeta(
        dev_mode=settings.dev_mode,
        version=settings.version,
        git_commit=settings.git_commit,
        data_version=settings.data_version,
        quant_core_root=settings.quant_core_root,
        artifacts_root=settings.artifacts_root,
    )


# ----------------- Listings & Introspection ---------------------


class FileEntry(BaseModel):
    path: str
    name: str
    size: int
    mtime: float


def _scan(root: Path, exts: tuple[str, ...], max_depth=4) -> list[FileEntry]:
    out: list[FileEntry] = []
    if not root.exists() or not root.is_dir():
        return out
    base_len = len(root.parts)
    for dp, _dirs, files in os.walk(root):
        depth = len(Path(dp).parts) - base_len
        if depth > max_depth:
            continue
        for f in files:
            if not f.lower().endswith(exts):
                continue
            p = Path(dp) / f
            try:
                st = p.stat()
                out.append(
                    FileEntry(
                        path=str(p.resolve()),
                        name=f,
                        size=st.st_size,
                        mtime=st.st_mtime,
                    )
                )
            except Exception:
                continue
    return out


@router.get("/list/runsdb", response_model=list[FileEntry])
async def list_runs_db():
    settings = get_settings()
    roots = []
    if settings.quant_core_root:
        roots.append(Path(settings.quant_core_root))
    roots.append(Path("."))
    seen: set[str] = set()
    out: list[FileEntry] = []
    for r in roots:
        for entry in _scan(r, (".sqlite",), max_depth=3):
            if entry.name == "runs.sqlite" or entry.name.endswith("_runs.sqlite"):
                if entry.path not in seen:
                    seen.add(entry.path)
                    out.append(entry)
    return sorted(out, key=lambda e: -e.mtime)[:50]


@router.get("/list/signals", response_model=list[FileEntry])
async def list_signals():
    settings = get_settings()
    roots = []
    if settings.quant_core_root:
        roots.append(Path(settings.quant_core_root) / "artifacts" / "signals")
    roots.append(Path("artifacts/signals"))
    out: list[FileEntry] = []
    seen: set[str] = set()
    for r in roots:
        for entry in _scan(r, (".parquet", ".pq")):
            if entry.path not in seen:
                seen.add(entry.path)
                out.append(entry)
    return sorted(out, key=lambda e: -e.mtime)[:200]


@router.get("/list/returns", response_model=list[FileEntry])
async def list_returns():
    settings = get_settings()
    roots = []
    if settings.quant_core_root:
        roots.append(Path(settings.quant_core_root) / "data_curated")
    roots.append(Path("data_curated"))
    out: list[FileEntry] = []
    seen: set[str] = set()
    for r in roots:
        for entry in _scan(r, (".parquet", ".pq")):
            if "return" in entry.name.lower() or "returns" in entry.name.lower():
                if entry.path not in seen:
                    seen.add(entry.path)
                    out.append(entry)
    return sorted(out, key=lambda e: -e.mtime)[:200]


@router.get("/list/strategies_cfg", response_model=list[FileEntry])
async def list_strategies_cfg():
    settings = get_settings()
    roots = []
    if settings.quant_core_root:
        roots.append(Path(settings.quant_core_root) / "configs")
    roots.append(Path("configs"))
    out: list[FileEntry] = []
    seen: set[str] = set()
    for r in roots:
        for entry in _scan(r, (".json",), max_depth=2):
            if "strateg" in entry.name.lower():
                if entry.path not in seen:
                    seen.add(entry.path)
                    out.append(entry)
    return sorted(out, key=lambda e: -e.mtime)[:100]


class ModeList(BaseModel):
    modes: list[str]
    default: str


@router.get("/introspect/modes", response_model=ModeList)
async def list_modes():
    return ModeList(modes=["long_only", "long_short"], default="long_short")


class MetricInfo(BaseModel):
    key: str
    label: str
    description: str


@router.get("/introspect/metrics", response_model=list[MetricInfo])
async def list_metrics():
    return [
        MetricInfo(
            key="sharpe",
            label="Sharpe",
            description="Risk-adjusted return (annualized return / annualized vol).",
        ),
        MetricInfo(
            key="cagr",
            label="CAGR",
            description="Compound annual growth rate of equity.",
        ),
        MetricInfo(
            key="max_dd",
            label="Max Drawdown",
            description="Maximum peak-to-trough equity decline.",
        ),
        MetricInfo(
            key="ann_vol",
            label="Annual Volatility",
            description="Standard deviation of returns annualized.",
        ),
        MetricInfo(
            key="ann_return",
            label="Annual Return",
            description="Geometric annualized return.",
        ),
    ]


class ConfigContent(BaseModel):
    path: str
    content: str


@router.get("/config/file", response_model=ConfigContent)
async def get_config_file(path: str):
    """Return the contents of a strategy configuration JSON file.

    Security: ensure path resides within an allowed root (configs under quant core root or local ./configs) and ends with .json.
    """
    settings = get_settings()
    p = Path(path).resolve()
    allowed: list[Path] = []
    if settings.quant_core_root:
        allowed.append(Path(settings.quant_core_root).resolve() / "configs")
    allowed.append(Path("configs").resolve())
    if p.suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="Only .json files allowed")
    try:
        parents_ok = any(str(p).startswith(str(a)) for a in allowed if a.exists())
    except Exception:
        parents_ok = False
    if not parents_ok:
        raise HTTPException(status_code=403, detail="Path outside allowed roots")
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        data = p.read_bytes()[:200_000].hex()
    if len(data) > 200_000:
        data = data[:200_000] + "\n...TRUNCATED..."
    return ConfigContent(path=str(p), content=data)


@router.get("/list/configs", response_model=list[FileEntry])
async def list_generic_configs():
    """List generic JSON config files (non-strategy) for use in dropdowns (e.g. walk-forward configs).

    Heuristic: scan configs/ (local and core) for *.json that do not match *strateg* to avoid duplicating strategy config list.
    """
    settings = get_settings()
    roots: list[Path] = []
    if settings.quant_core_root:
        roots.append(Path(settings.quant_core_root) / "configs")
    roots.append(Path("configs"))
    seen: set[str] = set()
    out: list[FileEntry] = []
    for r in roots:
        for entry in _scan(r, (".json",), max_depth=2):
            low = entry.name.lower()
            if "strateg" in low:
                continue
            if entry.path not in seen:
                seen.add(entry.path)
                out.append(entry)
    return sorted(out, key=lambda e: -e.mtime)[:100]


class CSVFile(BaseModel):
    path: str
    size: int
    mtime: float


@router.get("/datasets/csv", response_model=list[CSVFile])
async def list_csv_datasets():
    """Enumerate candidate CSV files under likely data roots (raw & curated).

    Search order:
      1. <QUANT_CORE_ROOT>/data_raw
      2. <QUANT_CORE_ROOT>/data_curated
      3. ./data_raw (relative to server cwd)
      4. ./data_curated
    Deduplicates by absolute path. Limited to depth=3 and *.csv.
    """
    settings = get_settings()
    roots: list[Path] = []
    if settings.quant_core_root:
        core = Path(settings.quant_core_root)
        roots += [core / "data_raw", core / "data_curated"]
    roots += [Path("./data_raw"), Path("./data_curated")]
    seen: set[Path] = set()
    results: list[CSVFile] = []
    for r in roots:
        if not r.exists() or not r.is_dir():
            continue
        try:
            # walk shallow
            for dirpath, dirnames, filenames in os.walk(r):
                depth = Path(dirpath).relative_to(r).parts
                if len(depth) > 3:
                    continue
                for f in filenames:
                    if not f.lower().endswith(".csv"):
                        continue
                    p = Path(dirpath) / f
                    ap = p.resolve()
                    if ap in seen:
                        continue
                    seen.add(ap)
                    stat = p.stat()
                    results.append(
                        CSVFile(path=str(ap), size=stat.st_size, mtime=stat.st_mtime)
                    )
        except Exception:  # pragma: no cover - best effort
            continue
    # Sort by most recent modified then size desc
    results.sort(key=lambda x: (-x.mtime, -x.size))
    # Cap to first 200 entries
    return results[:200]


# ----------------- Data Browser Endpoints ---------------------


class DomainMeta(BaseModel):
    domain: str
    rows: int
    cols: int
    type: str
    features: list[str]


class DomainsResponse(BaseModel):
    domains: list[DomainMeta]
    skipped: list[dict]


@router.get("/data/domains", response_model=DomainsResponse)
async def data_domains(refresh: bool = False):
    settings = get_settings()
    curated = (
        Path(settings.quant_core_root) / "data_curated"
        if settings.quant_core_root
        else Path("data_curated")
    )
    if not curated.exists():
        raise HTTPException(status_code=404, detail="curated root not found")
    try:
        reg = _get_registry(curated)
        if refresh:
            # crude refresh by resetting module-level cache
            import importlib

            regmod = importlib.import_module("src.data.registry")  # type: ignore
            regmod._def_registry = None  # reset
            reg = _get_registry(curated)
        reg.load_all()
        metas = []
        for d in reg.list_domains():
            dm = reg.domain_meta(d) or {}
            metas.append(
                DomainMeta(
                    domain=d,
                    rows=int(dm.get("rows", 0)),
                    cols=int(dm.get("cols", 0)),
                    type=dm.get("type", "unknown"),
                    features=list(dm.get("features", [])[:50]),
                )
            )
        skipped = reg.skipped_domains()
        return DomainsResponse(domains=metas, skipped=skipped)
    except RegistryError as e:  # type: ignore
        raise HTTPException(status_code=500, detail=str(e))


class DomainSample(BaseModel):
    domain: str
    columns: list[str]
    rows: list[dict]


@router.get("/data/sample", response_model=DomainSample)
async def data_sample(domain: str, limit: int = 50):
    settings = get_settings()
    curated = (
        Path(settings.quant_core_root) / "data_curated"
        if settings.quant_core_root
        else Path("data_curated")
    )
    reg = _get_registry(curated)
    df = reg.load_all()
    # isolate columns belonging to domain + date,ticker
    meta = reg.domain_meta(domain)
    if not meta:
        raise HTTPException(status_code=404, detail="domain not found")
    feat = meta.get("features", [])
    base_cols = ["date", "ticker"]
    cols = base_cols + feat
    sub = df[cols].head(limit)
    rows_out = []
    for _, r in sub.iterrows():
        item = {
            c: (
                r[c].isoformat()
                if hasattr(r[c], "isoformat")
                else (None if (pd is None or pd.isna(r[c])) else r[c])
            )
            for c in cols
        }
        rows_out.append(item)
    return DomainSample(domain=domain, columns=cols, rows=rows_out)


class FileListEntry(BaseModel):
    path: str
    kind: str
    size: int
    mtime: float


@router.get("/data/files", response_model=list[FileListEntry])
async def data_files(max_results: int = 400):
    settings = get_settings()
    roots = []
    if settings.quant_core_root:
        roots.append(Path(settings.quant_core_root) / "data_curated")
        roots.append(Path(settings.quant_core_root) / "configs")
        roots.append(Path(settings.quant_core_root) / "artifacts")
    roots += [Path("data_curated"), Path("configs"), Path("artifacts")]
    seen: set[str] = set()
    out: list[FileListEntry] = []
    exts = {
        ".parquet": "parquet",
        ".pq": "parquet",
        ".duckdb": "duckdb",
        ".sqlite": "sqlite",
        ".db": "sqlite",
        ".json": "json",
    }
    for root in roots:
        if not root.exists():
            continue
        for dp, _dirs, files in os.walk(root):
            for f in files:
                p = Path(dp) / f
                kind = exts.get(p.suffix.lower())
                if not kind:
                    continue
                ap = str(p.resolve())
                if ap in seen:
                    continue
                seen.add(ap)
                try:
                    st = p.stat()
                    out.append(
                        FileListEntry(
                            path=ap, kind=kind, size=st.st_size, mtime=st.st_mtime
                        )
                    )
                except Exception:
                    continue
    out.sort(key=lambda x: -x.mtime)
    return out[:max_results]


class FilePreview(BaseModel):
    path: str
    kind: str
    columns: list[str] | None = None
    rows: list[dict] | None = None
    text: str | None = None


@router.get("/data/file/preview", response_model=FilePreview)
async def data_file_preview(path: str, limit: int = 50, table: Optional[str] = None):
    p = Path(path).resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail="file not found")
    suffix = p.suffix.lower()
    if suffix in (".parquet", ".pq"):
        if pd is None:
            raise HTTPException(status_code=500, detail="pandas not installed")
        try:
            df = pd.read_parquet(p)  # type: ignore
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"parquet read failed: {e}")
        sub = df.head(limit)
        cols = list(sub.columns)
        rows = []
        for _, r in sub.iterrows():
            rows.append(
                {
                    c: (
                        r[c].isoformat()
                        if hasattr(r[c], "isoformat")
                        else (None if (pd is None or pd.isna(r[c])) else r[c])
                    )
                    for c in cols
                }
            )
        return FilePreview(path=str(p), kind="parquet", columns=cols, rows=rows)
    if suffix == ".json":
        try:
            txt = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return FilePreview(
                path=str(p), kind="json", text="<binary or invalid utf-8>"
            )
        if len(txt) > 200_000:
            txt = txt[:200_000] + "\n...TRUNCATED..."
        return FilePreview(path=str(p), kind="json", text=txt)
    if suffix in (".sqlite", ".db"):
        try:
            con = sqlite3.connect(str(p))
            cur = con.cursor()
            tables = [
                r[0]
                for r in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            if not tables:
                return FilePreview(path=str(p), kind="sqlite", text="(no tables)")
            t = table or tables[0]
            rows = cur.execute(f"SELECT * FROM {t} LIMIT {int(limit)}").fetchall()
            cols = [d[0] for d in cur.description]
            rows_dict = [dict(zip(cols, r)) for r in rows]
            meta_txt = f"tables: {tables}\nshowing table: {t}\n"
            return FilePreview(
                path=str(p), kind="sqlite", columns=cols, rows=rows_dict, text=meta_txt
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"sqlite preview failed: {e}")
    if suffix == ".duckdb":
        if duckdb is None:
            raise HTTPException(status_code=500, detail="duckdb not installed")
        try:
            con = duckdb.connect(str(p))  # type: ignore
            tbls = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
            if not tbls:
                return FilePreview(path=str(p), kind="duckdb", text="(no tables)")
            t = table or tbls[0]
            df = con.execute(f"SELECT * FROM {t} LIMIT {int(limit)}").fetchdf()
            rows = []
            for _idx, r in df.iterrows():  # type: ignore
                rows.append(
                    {
                        c: (
                            r[c].isoformat()
                            if hasattr(r[c], "isoformat")
                            else (None if (pd is None or pd.isna(r[c])) else r[c])
                        )
                        for c in df.columns
                    }
                )
            meta_txt = f"tables: {tbls}\nshowing table: {t}\n"
            return FilePreview(
                path=str(p),
                kind="duckdb",
                columns=list(df.columns),
                rows=rows,
                text=meta_txt,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"duckdb preview failed: {e}")
    raise HTTPException(status_code=400, detail="unsupported file type for preview")
