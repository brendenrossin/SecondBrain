"""FastAPI application entry point."""

import logging
import shutil
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from secondbrain import __version__
from secondbrain.api.admin import router as admin_router
from secondbrain.api.ask import router as ask_router
from secondbrain.api.briefing import router as briefing_router
from secondbrain.api.capture import router as capture_router
from secondbrain.api.conversations import router as conversations_router
from secondbrain.api.events import router as events_router
from secondbrain.api.index import router as index_router
from secondbrain.api.metadata import router as metadata_router
from secondbrain.api.tasks import router as tasks_router
from secondbrain.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Log resolved configuration at startup for debugging."""
    s = get_settings()
    logger.info("SecondBrain starting — vault_path=%s, data_path=%s", s.vault_path, s.data_path)
    if not s.vault_path or not s.vault_path.exists():
        logger.error("VAULT PATH NOT CONFIGURED OR MISSING — APIs will return 503 errors")
    yield


app = FastAPI(
    title="SecondBrain",
    description="Semantic memory system for Obsidian vaults",
    version=__version__,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:7860", "http://127.0.0.1:7860"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=500)

# Include API routers
app.include_router(admin_router)
app.include_router(ask_router)
app.include_router(capture_router)
app.include_router(briefing_router)
app.include_router(conversations_router)
app.include_router(events_router)
app.include_router(index_router)
app.include_router(metadata_router)
app.include_router(tasks_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Return project information."""
    return {
        "name": "SecondBrain",
        "version": __version__,
        "description": "Semantic memory system for Obsidian vaults",
    }


@app.get("/health")
@app.get("/api/v1/health")
async def health() -> dict[str, Any]:
    """Health check endpoint with vault, disk, and sync status."""
    s = get_settings()

    checks: dict[str, Any] = {"status": "ok"}

    # Vault check
    if not s.vault_path or not s.vault_path.exists():
        checks["status"] = "error"
        checks["vault"] = "not configured or missing"
    else:
        checks["vault"] = "ok"

    # Disk space
    disk_path = s.data_path if s.data_path.exists() else Path(".")
    _, _, free = shutil.disk_usage(str(disk_path))
    free_gb = round(free / (1024**3), 2)
    checks["free_disk_gb"] = free_gb
    if free_gb < 1.0:
        if checks["status"] == "ok":
            checks["status"] = "warning"
        checks["disk"] = "low"

    # Sync freshness
    sync_marker = s.data_path / ".sync_completed"
    if sync_marker.exists():
        age_hours = (time.time() - sync_marker.stat().st_mtime) / 3600
        checks["last_sync_hours_ago"] = round(age_hours, 1)
        if age_hours > 25:
            checks["sync"] = "stale"
    else:
        checks["last_sync_hours_ago"] = None

    return checks
