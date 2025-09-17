# Quant UI Skeleton

This repository contains the scaffolding for a SvelteKit frontend and FastAPI backend described in
[`ARCHITECTURE_UI.md`](ARCHITECTURE_UI.md). Both applications are wired with placeholder data so that the integration
points can be exercised end-to-end before real quant research pipelines are available.

- `frontend/` – SvelteKit application with routes for the dashboard landing page and `/strategies` view.
- `backend/` – FastAPI service exposing the API surface enumerated in the architecture brief.

Consult the READMEs in each directory for setup instructions.

## Two-System Architecture (Read vs Produce)

This UI repository is **read-only presentation**. It does **not** generate strategies, equity curves, model artifacts, signals or datasets. All such artifacts are **produced exclusively** by the _quant core_ repository (`QUANT_CORE_ROOT`). The UI:

- Reads JSON strategy summaries / details.
- Reads equity / returns curves.
- Reads manifests, datasets, models, signals.
- Computes lightweight _derived_ display analytics (drawdowns, rolling stats) **in-memory only**.

It never:

- Runs backtests or DSL evaluation.
- Trains models or generates AI candidate expressions.
- Mutates curated data or writes artifacts.

If you find yourself needing to "generate" something while inside this repo, switch context to the quant core project, create / refresh the artifact there, and point environment variables (`QUANT_STRATEGIES_ROOT`, `QUANT_CURVES_ROOT`, `QUANT_ARTIFACTS_ROOT`) here to consume it.

Design rule: **UI PRESENTS – CORE PRODUCES.**
