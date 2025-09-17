# Quant UI Frontend

This SvelteKit project provides the user interface outlined in [`ARCHITECTURE_UI.md`](../ARCHITECTURE_UI.md). The layout includes
an application shell, a landing page summarising the roadmap, and a `/strategies` route that consumes the FastAPI service.

## Setup

```bash
cd frontend
npm install
npm run dev
```

By default the app expects the backend to be available at the same origin under the `/api` prefix. If the backend is not running,
the strategies page will fall back to inline placeholder data so that styling work can progress independently.

## Two-System Architecture Reminder

Frontend logic is limited to _presentation_ concerns. All computationally heavy or state‑mutating operations (backtests, AI
expression generation, model training, data ingestion) happen **only** in the quant core repository. This frontend:

- Fetches read-only JSON from the FastAPI adapter.
- Renders charts (equity, returns, drawdowns, rolling metrics) from already produced series.
- Performs lightweight client derivations (formatting, percentages, small aggregations) that do **not** constitute research artifact generation.

If a UI change seems to require producing new curves, returns, or metrics at build/run time, first add or refresh those artifacts upstream in quant core (or extend its pipelines), then simply consume them here through the existing API contract.

Mnemonic: **CORE produces • Adapter serves • Frontend displays**.
