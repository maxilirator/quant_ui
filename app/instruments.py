from __future__ import annotations

from pathlib import Path
from typing import Optional


def _split_line(line: str) -> list[str]:
    stripped = line.strip()
    if "," in stripped:
        return [part.strip() for part in stripped.split(",") if part.strip()]
    return stripped.split()


def load_instruments(path: Path, instrument_type: str) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            parts = _split_line(line)
            if not parts:
                continue

            ticker = parts[0].lower()
            start: Optional[str] = parts[1] if len(parts) > 1 else None
            end: Optional[str] = parts[2] if len(parts) > 2 else None

            records.append(
                {
                    "ticker": ticker,
                    "start": start,
                    "end": end,
                    "type": instrument_type,
                }
            )

    return records
