"""Artifact manifest builder.

Produces artifacts/manifest.json summarising available models, reports, signals,
logs, strategies with content hashes and lightweight metadata. Designed for a
separate consumer (FastAPI service or other process) to read once and serve.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Dict, Any
import hashlib
import json
import time

from .atomic import atomic_write_json

DEFAULT_DIRS = ["models", "reports", "signals", "logs", "datasets", "strategies"]


@dataclass(frozen=True)
class FileEntry:
    file: str
    sha256: str
    size: int
    created: str
    kind: str | None = None
    extra: Dict[str, Any] | None = None


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _gather_dir(base: Path, sub: str) -> List[FileEntry]:
    out: List[FileEntry] = []
    d = base / sub
    if not d.exists():
        return out
    for p in sorted(d.rglob("*")):
        if p.is_dir():
            continue
        if p.suffix in {".tmp"}:  # skip temp
            continue
        rel = p.relative_to(base).as_posix()
        stat = p.stat()
        # Basic metadata (special cases can be added later based on extension)
        fe = FileEntry(
            file=rel,
            sha256=sha256_file(p),
            size=stat.st_size,
            created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
            kind=sub.rstrip("s"),
            extra=None,
        )
        out.append(fe)
    return out


def build_manifest(
    artifacts_root: str | Path,
    *,
    git_commit: str | None = None,
    data_version: str | None = None,
) -> dict:
    base = Path(artifacts_root)
    manifest: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": git_commit,
        "data_version": data_version,
        "entries": [],
        "version": 1,
    }
    entries: List[dict] = []
    for sub in DEFAULT_DIRS:
        entries.extend(asdict(e) for e in _gather_dir(base, sub))
    manifest["entries"] = entries
    return manifest


def write_manifest(artifacts_root: str | Path, manifest: dict) -> Path:
    root = Path(artifacts_root)
    target = root / "manifest.json"
    atomic_write_json(target, manifest, sort_keys=True)
    return target


def load_manifest(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


__all__ = [
    "build_manifest",
    "write_manifest",
    "load_manifest",
    "sha256_file",
    "FileEntry",
]
