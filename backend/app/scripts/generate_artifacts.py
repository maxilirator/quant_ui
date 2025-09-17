"""Utility script to generate JSON strategy + equity artifacts for UI isolation mode.

This script invokes the quant core (if importable) OR, as a fallback, runs the
`mvp_strategies` showcase in the sibling `quant` repository to produce:

  strategies_json/list.json
  strategies_json/<expr_hash>.json
  equity_curves/<expr_hash>.json

Assumptions
-----------
* QUANT_CORE_ROOT (or CORE_ROOT) points to the quant repo root (containing scripts/ & src/)
* A raw data CSV exists at data_raw/stock_history.csv (or user supplies --data)
* Equity curve can be approximated from cumulative returns if full curve isn't persisted.

If the quant core exposes richer APIs later (e.g. persistent runs DB), adapt this script
to query those directly.

Usage (PowerShell):
  $env:QUANT_CORE_ROOT="c:/dev/quant"
  python -m app.scripts.generate_artifacts --out-root c:/dev/quant_ui_artifacts --data c:/dev/quant/data_raw/stock_history.csv

Then point the UI API at that directory:
  $env:QUANT_STRATEGIES_ROOT="c:/dev/quant_ui_artifacts/strategies_json"
  $env:QUANT_CURVES_ROOT="c:/dev/quant_ui_artifacts/equity_curves"
  uvicorn app.main:app --reload
"""

from __future__ import annotations
import os, json, math, sys, subprocess, tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

UTC = timezone.utc

DEFAULT_EXPRESSIONS = [
    ("demo_momo", "cs_rank(ts_z(feat('r1'), 20))"),
    ("demo_meanrev", "-cs_rank(ts_z(feat('r1'), 5))"),
]


def _run_mvp(quant_root: Path, data_path: Path) -> List[Dict[str, Any]]:
    script = quant_root / "scripts" / "mvp_strategies.py"
    if not script.exists():
        raise RuntimeError(f"Cannot locate mvp_strategies.py under {script}")
    cmd = [sys.executable, str(script), "--data", str(data_path), "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mvp_strategies failed: {proc.stderr}")
    try:
        return json.loads(proc.stdout)
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            f"Failed to parse mvp_strategies JSON: {e}\n{proc.stdout[:500]}"
        )


# (Reserved for future richer simulation path construction.)
# def _synthetic_equity(days: int, mean_daily: float, vol_daily: float) -> tuple[List[str], List[float]]:
#     import random
#     from datetime import timedelta
#     equity = [1.0]
#     dates: List[str] = []
#     today = datetime.utcnow().date()
#     for i in range(days):
#         r = random.gauss(mean_daily, vol_daily)
#         equity.append(equity[-1] * (1 + r))
#         dates.append(str(today - timedelta(days=days - i)))
#     return dates, equity[1:]


def generate(out_root: Path, quant_root: Path, data_path: Path) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    strategies_dir = out_root / "strategies_json"
    curves_dir = out_root / "equity_curves"
    strategies_dir.mkdir(exist_ok=True)
    curves_dir.mkdir(exist_ok=True)

    # Run MVP strategies script
    results = _run_mvp(quant_root, data_path)
    items = []
    for r in results:
        name = r["name"]
        expr_hash = name  # using name as stable identifier
        metrics = {
            "ann_return": (
                r.get("ann_sharpe", 0) * 0.08 + 0.05 if r.get("ann_sharpe") else 0.05
            ),
            "ann_vol": r.get("ann_vol") or 0.1,
            "ann_sharpe": r.get("ann_sharpe") or 0.5,
            "max_dd": r.get("max_dd") or -0.1,
        }
        created_at = datetime.now(UTC).isoformat()
        detail = {
            "expr_hash": expr_hash,
            "expr": r.get("expr"),
            "metrics": metrics,
            "complexity_score": len(expr_hash) * 1.0,
            "created_at": created_at,
            "tags": ["mvp"],
            "notes": "Generated via MVP script",
        }
        # Write detail file
        (strategies_dir / f"{expr_hash}.json").write_text(json.dumps(detail, indent=2))
        items.append(
            {
                k: detail[k]
                for k in [
                    "expr_hash",
                    "expr",
                    "metrics",
                    "complexity_score",
                    "created_at",
                ]
            }
        )

        # Build simple equity curve if none exists (here we fake with cumulative return approximation)
        # Prefer actual net cumulative if provided
        cum = r.get("cum_net") or 0
        days = r.get("days") or 200
        # simple geometric path: evenly distribute log return
        import math

        eq = []
        base = 1.0
        if days < 2:
            days = 2
        # assume cum is total return over period
        target = 1 + (cum or 0)
        step = target ** (1 / days)
        for _ in range(days):
            base *= step
            eq.append(base)
        dates = [datetime.now(UTC).date().isoformat() for _ in range(days)]
        curves_dir.mkdir(exist_ok=True)
        (curves_dir / f"{expr_hash}.json").write_text(
            json.dumps(
                {
                    "dates": dates,
                    "equity": [round(v, 6) for v in eq],
                    "base_currency": "SEK",
                },
                indent=2,
            )
        )

    # Write list.json
    list_payload = {"items": items}
    (strategies_dir / "list.json").write_text(json.dumps(list_payload, indent=2))
    print(f"Wrote {len(items)} strategies to {strategies_dir}")


def main():  # pragma: no cover
    from datetime import timedelta
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out-root",
        required=True,
        help="Root output dir for artifacts (will create strategies_json & equity_curves)",
    )
    ap.add_argument(
        "--quant-root",
        default=os.environ.get("QUANT_CORE_ROOT"),
        help="Path to quant core root",
    )
    ap.add_argument(
        "--data",
        default="data_raw/stock_history.csv",
        help="Path to raw stock history CSV",
    )
    args = ap.parse_args()
    if not args.quant_root:
        print("ERROR: --quant-root or QUANT_CORE_ROOT required", file=sys.stderr)
        return 2
    quant_root = Path(args.quant_root)
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"ERROR: data file not found: {data_path}", file=sys.stderr)
        return 3
    out_root = Path(args.out_root)
    generate(out_root, quant_root, data_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
