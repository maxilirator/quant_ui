"""Entrypoint for the Quant UI FastAPI application."""

from fastapi import FastAPI, Request, HTTPException
import sys
from pathlib import Path

from app.api import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.version)

# Dynamically add external quant core path to sys.path if provided
if settings.quant_core_root:
    core_path = Path(settings.quant_core_root).resolve()
    if core_path.is_dir():
        if str(core_path) not in sys.path:
            sys.path.insert(0, str(core_path))
    else:
        # Leave a breadcrumb in app state for debugging; real logging infra TBD
        app.state.quant_core_missing = str(core_path)


READ_ONLY_ALLOWED_METHODS = {"GET", "HEAD", "OPTIONS", "WEBSOCKET"}
CONTROL_PREFIX = "/api/control"


@app.middleware("http")
async def read_only_guard(request: Request, call_next):  # pragma: no cover simple logic
    method = request.method.upper()
    path = request.url.path
    # Allow control routes to use POST/other methods (they are explicitly whitelisted internally)
    if not path.startswith(CONTROL_PREFIX) and method not in READ_ONLY_ALLOWED_METHODS:
        raise HTTPException(
            status_code=405, detail="Read-only mode: method not allowed"
        )
    # Optional API key header enforcement for artifacts endpoints
    api_key_setting = settings.api_key
    if api_key_setting and request.url.path.startswith("/api/artifacts"):
        provided = request.headers.get("X-API-Key")
        if not provided or provided != api_key_setting:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    response = await call_next(request)
    return response


@app.get("/", tags=["health"], summary="Service landing endpoint")
async def read_root() -> dict[str, str]:
    """Provide a simple landing payload for the root path."""

    return {"message": "Quant UI service is running", "docs_url": "/docs"}


app.include_router(api_router, prefix="/api")

# Import and mount control router after main API include to ensure middleware sees prefix
from app.api.v1.control import router as control_router  # noqa: E402

app.include_router(control_router, prefix="/api")
