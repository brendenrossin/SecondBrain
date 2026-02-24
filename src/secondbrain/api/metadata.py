"""API endpoints for metadata extraction and suggestions."""

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from secondbrain.api.dependencies import (
    get_extractor,
    get_metadata_store,
    get_settings,
    get_suggestion_engine,
)
from secondbrain.config import Settings
from secondbrain.extraction.extractor import MetadataExtractor
from secondbrain.models import NoteMetadata, NoteSuggestions
from secondbrain.stores.metadata import MetadataStore
from secondbrain.suggestions.engine import SuggestionEngine
from secondbrain.vault.connector import VaultConnector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["metadata"])


class ExtractResponse(BaseModel):
    """Response for extraction operations."""

    status: str
    notes_extracted: int
    notes_skipped: int
    notes_failed: int
    message: str


@router.get("/metadata/{note_path:path}", response_model=NoteMetadata)
async def get_note_metadata(
    note_path: str,
    metadata_store: Annotated[MetadataStore, Depends(get_metadata_store)],
) -> NoteMetadata:
    """Get extracted metadata for a specific note."""
    result = metadata_store.get(note_path)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No metadata for note: {note_path}")
    return result


@router.get("/metadata", response_model=list[NoteMetadata])
async def list_metadata(
    metadata_store: Annotated[MetadataStore, Depends(get_metadata_store)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[NoteMetadata]:
    """List all extracted metadata (paginated)."""
    all_meta = metadata_store.get_all()
    return all_meta[offset : offset + limit]


@router.post("/extract", response_model=ExtractResponse)
async def extract_metadata(
    settings: Annotated[Settings, Depends(get_settings)],
    metadata_store: Annotated[MetadataStore, Depends(get_metadata_store)],
    extractor: Annotated[MetadataExtractor, Depends(get_extractor)],
    note_path: str | None = Query(default=None),
    force: bool = Query(default=False),
) -> ExtractResponse:
    """Extract metadata for vault notes.

    If note_path is set, extract only that note. Otherwise extract all stale notes.
    If force is True, re-extract even if metadata exists and hash matches.
    """
    if not settings.vault_path:
        raise HTTPException(status_code=400, detail="Vault path not configured")

    vault_path = Path(settings.vault_path)
    if not vault_path.exists():
        raise HTTPException(status_code=400, detail=f"Vault path does not exist: {vault_path}")

    connector = VaultConnector(vault_path)

    if note_path:
        # Single note extraction (blocking LLM call — run in thread)
        try:
            note = connector.read_note(Path(note_path))
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Note not found: {e}") from e

        metadata = await asyncio.to_thread(extractor.extract, note)
        # Override extractor's content hash with raw-bytes hash to match
        # VaultConnector.get_file_metadata() used for staleness checks.
        full_path = vault_path / note_path
        metadata.content_hash = hashlib.sha1(full_path.read_bytes()).hexdigest()
        metadata_store.upsert(metadata)
        return ExtractResponse(
            status="success",
            notes_extracted=1,
            notes_skipped=0,
            notes_failed=0,
            message=f"Extracted metadata for {note_path}",
        )

    # Batch extraction: find stale notes
    vault_files = connector.get_file_metadata()
    current_hashes = {path: h for path, (_mtime, h) in vault_files.items()}

    stale_paths = list(current_hashes.keys()) if force else metadata_store.get_stale(current_hashes)

    if not stale_paths:
        return ExtractResponse(
            status="success",
            notes_extracted=0,
            notes_skipped=len(vault_files),
            notes_failed=0,
            message="All notes up to date",
        )

    # Batch extraction loop is blocking (file I/O + LLM calls) — run in thread
    def _extract_batch() -> tuple[int, int]:
        _extracted = 0
        _failed = 0
        for path in stale_paths:
            try:
                note = connector.read_note(Path(path))
                metadata = extractor.extract(note)
                metadata.content_hash = current_hashes[path]  # Match get_file_metadata() hash
                metadata_store.upsert(metadata)
                _extracted += 1
            except Exception:
                logger.warning("Failed to extract %s", path, exc_info=True)
                _failed += 1
        return _extracted, _failed

    extracted, failed = await asyncio.to_thread(_extract_batch)

    skipped = len(vault_files) - extracted - failed
    return ExtractResponse(
        status="success",
        notes_extracted=extracted,
        notes_skipped=skipped,
        notes_failed=failed,
        message=f"Extracted {extracted}, skipped {skipped}, failed {failed}",
    )


@router.get("/suggestions/{note_path:path}", response_model=NoteSuggestions)
async def get_suggestions(
    note_path: str,
    engine: Annotated[SuggestionEngine, Depends(get_suggestion_engine)],
) -> NoteSuggestions:
    """Get suggestions (related notes, links, tags) for a note."""
    result = engine.suggest(note_path)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No metadata for note: {note_path}. Run extraction first.",
        )
    return result


@router.get("/entities")
async def list_entities(
    metadata_store: Annotated[MetadataStore, Depends(get_metadata_store)],
    entity_type: str | None = Query(default=None),
) -> dict[str, object]:
    """List all entities across the vault, optionally filtered by type."""
    all_meta = metadata_store.get_all()
    entities: list[dict[str, object]] = []
    for meta in all_meta:
        for entity in meta.entities:
            if entity_type and entity.entity_type != entity_type:
                continue
            entities.append(
                {
                    "text": entity.text,
                    "entity_type": entity.entity_type,
                    "confidence": entity.confidence,
                    "note_path": meta.note_path,
                }
            )

    return {"entities": entities, "total": len(entities)}


@router.get("/action-items")
async def list_action_items(
    metadata_store: Annotated[MetadataStore, Depends(get_metadata_store)],
) -> dict[str, object]:
    """List all action items across the vault."""
    all_meta = metadata_store.get_all()
    items: list[dict[str, object]] = []
    for meta in all_meta:
        for action in meta.action_items:
            items.append(
                {
                    "text": action.text,
                    "confidence": action.confidence,
                    "priority": action.priority,
                    "note_path": meta.note_path,
                }
            )

    # Sort by priority (high first)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: priority_order.get(str(x.get("priority", "")), 3))

    return {"action_items": items, "total": len(items)}
