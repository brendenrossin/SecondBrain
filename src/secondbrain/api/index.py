"""Index endpoint for triggering vault indexing."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from secondbrain.api.dependencies import (
    get_embedder,
    get_index_tracker,
    get_lexical_store,
    get_settings,
    get_vector_store,
)
from secondbrain.config import Settings
from secondbrain.indexing.chunker import Chunker
from secondbrain.indexing.embedder import Embedder
from secondbrain.stores.index_tracker import IndexTracker
from secondbrain.stores.lexical import LexicalStore
from secondbrain.stores.vector import VectorStore
from secondbrain.vault.connector import VaultConnector

router = APIRouter(prefix="/api/v1", tags=["index"])


class IndexResponse(BaseModel):
    """Response for indexing operations."""

    status: str
    notes_processed: int
    chunks_created: int
    message: str


class IndexStatsResponse(BaseModel):
    """Response for index statistics."""

    vector_count: int
    lexical_count: int


@router.post("/index", response_model=IndexResponse)
async def index_vault(
    settings: Annotated[Settings, Depends(get_settings)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    lexical_store: Annotated[LexicalStore, Depends(get_lexical_store)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    tracker: Annotated[IndexTracker, Depends(get_index_tracker)],
    full_rebuild: bool = False,
) -> IndexResponse:
    """Index the vault. Uses incremental indexing by default.

    Args:
        full_rebuild: If True, clear the tracker and do a full reindex.
    """
    if not settings.vault_path:
        raise HTTPException(
            status_code=400,
            detail="Vault path not configured. Set SECONDBRAIN_VAULT_PATH environment variable.",
        )

    vault_path = Path(settings.vault_path)
    if not vault_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Vault path does not exist: {vault_path}",
        )

    connector = VaultConnector(vault_path)
    chunker = Chunker()

    if full_rebuild:
        tracker.clear()
        vector_store.clear()
        lexical_store.clear()

    # Get file metadata and classify changes
    vault_files = connector.get_file_metadata()
    if not vault_files:
        return IndexResponse(
            status="success",
            notes_processed=0,
            chunks_created=0,
            message="No notes found in vault",
        )

    new_files, modified_files, deleted_files, unchanged_files = tracker.classify_changes(vault_files)

    # Delete chunks for deleted + modified files
    for file_path in deleted_files + modified_files:
        vector_store.delete_by_note_path(file_path)
        lexical_store.delete_by_note_path(file_path)
        if file_path in deleted_files:
            tracker.remove_file(file_path)

    # Index new + modified files
    files_to_index = new_files + modified_files
    total_chunks = 0
    for file_path in files_to_index:
        try:
            note = connector.read_note(Path(file_path))
        except Exception:
            continue
        chunks = chunker.chunk_note(note)
        if chunks:
            texts = [c.chunk_text for c in chunks]
            embeddings = embedder.embed(texts)
            vector_store.add_chunks(chunks, embeddings)
            lexical_store.add_chunks(chunks)

        mtime, content_hash = vault_files[file_path]
        tracker.mark_indexed(file_path, content_hash, mtime, len(chunks))
        total_chunks += len(chunks)

    return IndexResponse(
        status="success",
        notes_processed=len(files_to_index),
        chunks_created=total_chunks,
        message=(
            f"Incremental index: {len(new_files)} new, {len(modified_files)} modified, "
            f"{len(deleted_files)} deleted, {len(unchanged_files)} unchanged "
            f"({total_chunks} chunks)"
        ),
    )


@router.get("/index/stats", response_model=IndexStatsResponse)
async def index_stats(
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    lexical_store: Annotated[LexicalStore, Depends(get_lexical_store)],
) -> IndexStatsResponse:
    """Get index statistics."""
    return IndexStatsResponse(
        vector_count=vector_store.count(),
        lexical_count=lexical_store.count(),
    )


@router.delete("/index")
async def clear_index(
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    lexical_store: Annotated[LexicalStore, Depends(get_lexical_store)],
) -> dict[str, str]:
    """Clear all indexed data."""
    vector_store.clear()
    lexical_store.clear()
    return {"status": "success", "message": "Index cleared"}
