"""Index endpoint for triggering vault indexing."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from secondbrain.api.dependencies import (
    get_embedder,
    get_lexical_store,
    get_settings,
    get_vector_store,
)
from secondbrain.config import Settings
from secondbrain.indexing.chunker import Chunker
from secondbrain.indexing.embedder import Embedder
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
) -> IndexResponse:
    """Index the entire vault."""
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

    # Initialize components
    connector = VaultConnector(vault_path)
    chunker = Chunker()

    # Read all notes
    notes = connector.read_all_notes()
    if not notes:
        return IndexResponse(
            status="success",
            notes_processed=0,
            chunks_created=0,
            message="No notes found in vault",
        )

    # Chunk all notes
    all_chunks = []
    for note in notes:
        chunks = chunker.chunk_note(note)
        all_chunks.extend(chunks)

    if not all_chunks:
        return IndexResponse(
            status="success",
            notes_processed=len(notes),
            chunks_created=0,
            message="No chunks created from notes",
        )

    # Generate embeddings
    texts = [c.chunk_text for c in all_chunks]
    embeddings = embedder.embed(texts)

    # Store in vector store
    vector_store.add_chunks(all_chunks, embeddings)

    # Store in lexical store
    lexical_store.add_chunks(all_chunks)

    return IndexResponse(
        status="success",
        notes_processed=len(notes),
        chunks_created=len(all_chunks),
        message=f"Successfully indexed {len(notes)} notes into {len(all_chunks)} chunks",
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
