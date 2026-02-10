"""FastAPI application entry point."""

from fastapi import FastAPI

from secondbrain import __version__
from secondbrain.api.admin import router as admin_router
from secondbrain.api.ask import router as ask_router
from secondbrain.api.briefing import router as briefing_router
from secondbrain.api.capture import router as capture_router
from secondbrain.api.conversations import router as conversations_router
from secondbrain.api.index import router as index_router
from secondbrain.api.metadata import router as metadata_router
from secondbrain.api.tasks import router as tasks_router
from secondbrain.config import get_settings

settings = get_settings()

app = FastAPI(
    title="SecondBrain",
    description="Semantic memory system for Obsidian vaults",
    version=__version__,
    debug=settings.debug,
)

# Include API routers
app.include_router(admin_router)
app.include_router(ask_router)
app.include_router(capture_router)
app.include_router(briefing_router)
app.include_router(conversations_router)
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
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
