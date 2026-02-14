"""Quick capture endpoint: write text directly to the Inbox folder."""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from secondbrain.api.dependencies import get_metadata_store, get_retriever, get_settings
from secondbrain.models import CaptureConnection, CaptureRequest, CaptureResponse
from secondbrain.retrieval.hybrid import RetrievalCandidate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["capture"])


@router.post("/capture", response_model=CaptureResponse)
async def capture(request: CaptureRequest) -> CaptureResponse:
    """Write captured text to the Inbox as a timestamped Markdown file.

    The file will be picked up by the inbox processor on the next sync.
    """
    settings = get_settings()
    if not settings.vault_path:
        raise HTTPException(status_code=500, detail="SECONDBRAIN_VAULT_PATH not configured")

    inbox_dir = settings.vault_path / "Inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%d_%H%M%S")
    filename = f"capture_{timestamp}.md"
    filepath = inbox_dir / filename

    # Avoid overwriting if two captures happen in the same second
    if filepath.exists():
        filename = f"capture_{timestamp}_{now.microsecond}.md"
        filepath = inbox_dir / filename

    filepath.write_text(request.text, encoding="utf-8")
    logger.info("Captured to %s (%d chars)", filename, len(request.text))

    # Surface related notes from the vault (blocking I/O — run in thread)
    connections: list[CaptureConnection] = []
    try:
        retriever = get_retriever()
        candidates = await asyncio.to_thread(retriever.retrieve, request.text, 10)

        # Deduplicate by note_path, keep highest RRF score
        seen: dict[str, RetrievalCandidate] = {}
        for c in candidates:
            if c.note_path not in seen or c.rrf_score > seen[c.note_path].rrf_score:
                seen[c.note_path] = c

        top = sorted(seen.values(), key=lambda c: c.rrf_score, reverse=True)[:5]

        # Try to load metadata store for richer snippets
        metadata_store = None
        with contextlib.suppress(Exception):
            metadata_store = get_metadata_store()

        for c in top:
            snippet = c.chunk_text[:150].strip()
            if metadata_store:
                try:
                    meta = metadata_store.get(c.note_path)
                    if meta and meta.summary:
                        snippet = meta.summary
                except Exception:
                    pass
            connections.append(
                CaptureConnection(
                    note_path=c.note_path,
                    note_title=c.note_title,
                    snippet=snippet,
                    score=round(c.rrf_score, 4),
                )
            )
    except Exception:
        logger.debug("Connection surfacing failed, returning capture without connections")

    return CaptureResponse(
        filename=filename,
        message=f"Captured to Inbox/{filename}",
        connections=connections,
    )
