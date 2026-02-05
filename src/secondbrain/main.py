"""FastAPI application entry point."""

from fastapi import FastAPI

from secondbrain import __version__
from secondbrain.api.ask import router as ask_router
from secondbrain.api.index import router as index_router
from secondbrain.config import get_settings

settings = get_settings()

app = FastAPI(
    title="SecondBrain",
    description="Semantic memory system for Obsidian vaults",
    version=__version__,
    debug=settings.debug,
)

# Include API routers
app.include_router(ask_router)
app.include_router(index_router)


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
