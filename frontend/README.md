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
