"""Entrypoint for the Quant UI FastAPI application."""

from fastapi import FastAPI

from app.api import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.version)


@app.get("/", tags=["health"], summary="Service landing endpoint")
async def read_root() -> dict[str, str]:
    """Provide a simple landing payload for the root path."""

    return {"message": "Quant UI service is running", "docs_url": "/docs"}


app.include_router(api_router, prefix="/api")
