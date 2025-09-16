"""Data contract enforcement utilities (strict partition & schema validation).

This module provides a minimal scaffold for validating curated parquet directory
structures before higher-level DSL / backtest operations.

Planned domains (Hive-style key=value partitions unless noted):
- bars_eod: ticker=SYM/year=YYYY
- universe_membership: year=YYYY
- fx_rates: ccy_pair=PAIR
- cost_model_daily: year=YYYY
- trading_calendar: year=YYYY
- asset_master: ticker=SYM (static)

This initial scaffold focuses on directory shape & basic file presence, not
column-level validation (to be added in test suite tasks).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass(frozen=True)
class PartitionIssue:
    domain: str
    path: str
    kind: str  # e.g. missing_domain, bad_partition, unexpected_plain_dir
    detail: str


REQUIRED_DOMAINS = {
    "bars_eod": ("ticker", "year"),
    "universe_membership": ("year",),
    "fx_rates": ("ccy_pair",),
    "cost_model_daily": ("year",),
    "trading_calendar": ("year",),
    "asset_master": ("ticker",),  # treated as single-level
}


def _is_key_value_dir(name: str) -> bool:
    return (
        "=" in name
        and len(name.split("=")) == 2
        and all(part for part in name.split("="))
    )


def scan_curated_root(root: Path) -> List[PartitionIssue]:
    issues: List[PartitionIssue] = []
    if not root.exists():
        issues.append(
            PartitionIssue(
                "_root", str(root), "missing_root", "Curated root does not exist"
            )
        )
        return issues
    for domain, expected_keys in REQUIRED_DOMAINS.items():
        domain_path = root / domain
        if not domain_path.exists():
            issues.append(
                PartitionIssue(
                    domain,
                    str(domain_path),
                    "missing_domain",
                    "Domain directory missing",
                )
            )
            continue
        # Single level domains (asset_master) just need child partition dirs
        for child in domain_path.iterdir():
            if child.is_dir():
                if domain == "asset_master":
                    if not _is_key_value_dir(child.name):
                        issues.append(
                            PartitionIssue(
                                domain,
                                str(child),
                                "unexpected_plain_dir",
                                "Expected key=value partition",
                            )
                        )
                    continue
                # Multi-level: first level must be key=value
                if not _is_key_value_dir(child.name):
                    issues.append(
                        PartitionIssue(
                            domain,
                            str(child),
                            "unexpected_plain_dir",
                            "Expected key=value partition",
                        )
                    )
            # files at top level are currently tolerated for trading_calendar (future warning)
    return issues


def summarize(issues: Iterable[PartitionIssue]) -> str:
    lines = [f"{i.domain}: {i.kind} {i.path} - {i.detail}" for i in issues]
    return "\n".join(lines)


__all__ = ["scan_curated_root", "PartitionIssue", "summarize", "REQUIRED_DOMAINS"]
