"""API route modules."""

from secondbrain.api.ask import router as ask_router
from secondbrain.api.index import router as index_router

__all__ = ["ask_router", "index_router"]
