"""Atomic write utilities for artifact persistence.

Usage:
    from app.artifacts.atomic import atomic_write_text
    atomic_write_text(target_path, json_string)

Guarantees:
- Write is performed to <path>.tmp and then atomically renamed.
- Intermediate .tmp files can be ignored safely by consumers.
"""

from __future__ import annotations

from pathlib import Path
import os
import tempfile
from typing import Union


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Use temporary file in same directory to ensure atomic rename on same filesystem.
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def atomic_write_text(
    path: Union[str, Path], text: str, encoding: str = "utf-8"
) -> None:
    p = Path(path)
    _atomic_write_bytes(p, text.encode(encoding))


def atomic_write_json(path: Union[str, Path], obj, *, sort_keys: bool = False) -> None:
    import json

    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=sort_keys))


__all__ = ["atomic_write_text", "atomic_write_json"]
