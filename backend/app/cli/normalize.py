"""Normalization CLI for legacy directory layouts -> key=value partitions.

Currently a placeholder: detects plain subdirectories under known domains and
prints a plan (no rename yet). Future implementation will perform atomic
renames (temp + replace) and idempotent re-runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import List
import typer

from app.data.contract import REQUIRED_DOMAINS

app = typer.Typer(add_completion=False, help="Normalization utilities for curated data")


def _plan_normalize(domain_path: Path) -> List[tuple[str, str]]:
    plan: List[tuple[str, str]] = []
    for child in domain_path.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        # Already key=value
        if "=" in name:
            continue
        # Infer key based on domain heuristics
        key = None
        if domain_path.name == "fx_rates":
            key = "ccy_pair"
        elif domain_path.name == "exogener":
            key = "series"
        elif domain_path.name == "universe_membership":
            key = "year" if name.isdigit() else None
        elif domain_path.name == "asset_master":
            key = "ticker"
        elif domain_path.name == "bars_eod":
            # If we see a plain ticker, we need an intermediate year layer later; skip for now
            key = "ticker"
        if key:
            plan.append((str(child), f"{child.parent / (key + '=' + name)}"))
    return plan


@app.command()
def dry_run(
    curated: Path = typer.Argument(
        ..., exists=True, file_okay=False, dir_okay=True, readable=True
    )
):
    """Show planned renames without performing them."""
    total = 0
    for domain in sorted(REQUIRED_DOMAINS.keys() | {"exogener"}):
        dpath = curated / domain
        if not dpath.exists():
            continue
        plan = _plan_normalize(dpath)
        if plan:
            typer.echo(f"DOMAIN {domain}")
            for src, dst in plan:
                typer.echo(f"  PLAN {src} -> {dst}")
                total += 1
    if total == 0:
        typer.echo("No normalization actions planned.")


def main():  # pragma: no cover
    app()  # noqa


if __name__ == "__main__":  # pragma: no cover
    main()
