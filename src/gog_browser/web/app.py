"""Minimal FastAPI app entry."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gog_browser.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="GOG Games Browser", version="0.1.0", lifespan=lifespan)


def mount_static_and_routes():
    """Mount static assets and include API router."""
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    from gog_browser.web.routes import api_router
    app.include_router(api_router, prefix="/api", tags=["api"])


@app.get("/")
async def root():
    """Serve the main UI (index.html) or fallback."""
    index = Path(__file__).parent / "static" / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "GOG Games Browser", "docs": "/docs"}


mount_static_and_routes()
