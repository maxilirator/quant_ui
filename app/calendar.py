from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime
from pathlib import Path


def load_calendar(path: Path) -> list[str]:
    dates: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                datetime.strptime(line, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError(f"Invalid calendar date: {line}") from exc
            dates.append(line)

    if not dates:
        raise ValueError("Calendar is empty")

    return dates


def build_calendar_index(calendar: list[str]) -> dict[str, int]:
    return {date: idx for idx, date in enumerate(calendar)}


def slice_calendar(
    calendar: list[str], calendar_index: dict[str, int], start: str, end: str
) -> list[str]:
    if start > end:
        raise ValueError("from date is after to date")

    start_idx = calendar_index.get(start)
    if start_idx is None:
        start_idx = bisect_left(calendar, start)

    end_idx = calendar_index.get(end)
    if end_idx is None:
        end_idx = bisect_right(calendar, end) - 1

    start_idx = max(0, min(start_idx, len(calendar)))
    end_idx = max(-1, min(end_idx, len(calendar) - 1))
    if start_idx > end_idx:
        return []

    return calendar[start_idx : end_idx + 1]
