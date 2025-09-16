"""CLI to build artifacts/manifest.json.

Example:
  python -m app.cli.build_manifest --artifacts artifacts --git $(git rev-parse --short HEAD) \
      --data-version 20250915_fund_v2
"""

from __future__ import annotations

import typer
from pathlib import Path
from app.artifacts.manifest import build_manifest, write_manifest

app = typer.Typer(add_completion=False)


@app.command()
def build(
    artifacts: Path = typer.Option(Path("artifacts"), help="Artifacts root directory"),
    git: str | None = typer.Option(None, help="Git commit (short)"),
    data_version: str | None = typer.Option(None, help="Data version identifier"),
):
    manifest = build_manifest(artifacts, git_commit=git, data_version=data_version)
    target = write_manifest(artifacts, manifest)
    typer.echo(f"Wrote manifest: {target}")


def main():  # pragma: no cover
    app()  # noqa


if __name__ == "__main__":  # pragma: no cover
    main()
