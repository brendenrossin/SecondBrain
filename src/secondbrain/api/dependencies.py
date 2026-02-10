"""FastAPI dependency injection for shared resources."""

import logging
from functools import lru_cache
from pathlib import Path

from secondbrain.config import Settings
from secondbrain.extraction.extractor import MetadataExtractor
from secondbrain.indexing.embedder import (
    Embedder,
    EmbeddingProvider,
    OpenAIEmbeddingProvider,
    SentenceTransformerProvider,
    build_embedding_text,
    extract_note_metadata,
)
from secondbrain.logging.query_logger import QueryLogger
from secondbrain.retrieval.hybrid import HybridRetriever
from secondbrain.retrieval.reranker import LLMReranker
from secondbrain.scripts.llm_client import LLMClient
from secondbrain.stores.conversation import ConversationStore
from secondbrain.stores.index_tracker import IndexTracker
from secondbrain.stores.lexical import LexicalStore
from secondbrain.stores.metadata import MetadataStore
from secondbrain.stores.usage import UsageStore
from secondbrain.stores.vector import VectorStore
from secondbrain.suggestions.engine import SuggestionEngine
from secondbrain.synthesis.answerer import Answerer

logger = logging.getLogger(__name__)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


@lru_cache
def get_data_path() -> Path:
    """Get the data directory path."""
    settings = get_settings()
    data_path = Path(settings.data_path) if settings.data_path else Path("data")
    data_path.mkdir(parents=True, exist_ok=True)
    return data_path


@lru_cache
def get_vector_store() -> VectorStore:
    """Get cached vector store instance."""
    data_path = get_data_path()
    return VectorStore(data_path / "chroma")


@lru_cache
def get_lexical_store() -> LexicalStore:
    """Get cached lexical store instance."""
    data_path = get_data_path()
    return LexicalStore(data_path / "lexical.db")


@lru_cache
def get_embedder() -> Embedder:
    """Get cached embedder instance based on configured provider."""
    settings = get_settings()
    provider: EmbeddingProvider
    if settings.embedding_provider == "openai":
        provider = OpenAIEmbeddingProvider(
            model_name=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
            dimensions=settings.openai_embedding_dimensions,
        )
    else:
        provider = SentenceTransformerProvider(model_name=settings.embedding_model)
    return Embedder(provider=provider)


@lru_cache
def get_conversation_store() -> ConversationStore:
    """Get cached conversation store instance."""
    data_path = get_data_path()
    return ConversationStore(data_path / "conversations.db")


@lru_cache
def get_query_logger() -> QueryLogger:
    """Get cached query logger instance."""
    data_path = get_data_path()
    return QueryLogger(data_path / "queries.jsonl")


@lru_cache
def get_metadata_store() -> MetadataStore:
    """Get cached metadata store instance."""
    settings = get_settings()
    data_path = get_data_path()
    return MetadataStore(data_path / settings.metadata_db_name)


@lru_cache
def get_usage_store() -> UsageStore:
    """Get cached usage store instance."""
    data_path = get_data_path()
    return UsageStore(data_path / "usage.db")


@lru_cache
def get_llm_client() -> LLMClient:
    """Get cached LLM client instance."""
    return LLMClient(usage_store=get_usage_store())


@lru_cache
def get_extractor() -> MetadataExtractor:
    """Get cached metadata extractor instance."""
    return MetadataExtractor(get_llm_client())


@lru_cache
def get_suggestion_engine() -> SuggestionEngine:
    """Get cached suggestion engine instance."""
    return SuggestionEngine(
        vector_store=get_vector_store(),
        metadata_store=get_metadata_store(),
        embedder=get_embedder(),
    )


@lru_cache
def get_index_tracker() -> IndexTracker:
    """Get cached index tracker instance."""
    data_path = get_data_path()
    return IndexTracker(data_path / "index_tracker.db")


@lru_cache
def get_retriever() -> HybridRetriever:
    """Get cached hybrid retriever instance."""
    return HybridRetriever(
        vector_store=get_vector_store(),
        lexical_store=get_lexical_store(),
        embedder=get_embedder(),
    )


@lru_cache
def get_reranker() -> LLMReranker:
    """Get cached reranker instance (Anthropic)."""
    settings = get_settings()
    return LLMReranker(
        model=settings.rerank_model,
        api_key=settings.anthropic_api_key,
        provider="anthropic",
        usage_store=get_usage_store(),
    )


@lru_cache
def get_openai_reranker() -> LLMReranker:
    """Get cached reranker instance (OpenAI)."""
    settings = get_settings()
    return LLMReranker(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
        provider="openai",
        usage_store=get_usage_store(),
    )


@lru_cache
def get_local_reranker() -> LLMReranker:
    """Get cached reranker instance (local Ollama)."""
    settings = get_settings()
    return LLMReranker(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        provider="openai",
        usage_store=get_usage_store(),
    )


@lru_cache
def get_answerer() -> Answerer:
    """Get cached answerer instance (Anthropic)."""
    settings = get_settings()
    return Answerer(
        model=settings.answer_model,
        api_key=settings.anthropic_api_key,
        provider="anthropic",
        usage_store=get_usage_store(),
    )


@lru_cache
def get_openai_answerer() -> Answerer:
    """Get cached answerer instance (OpenAI)."""
    settings = get_settings()
    return Answerer(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
        provider="openai",
        usage_store=get_usage_store(),
    )


@lru_cache
def get_local_answerer() -> Answerer:
    """Get cached answerer instance (local Ollama)."""
    settings = get_settings()
    return Answerer(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        provider="openai",
        usage_store=get_usage_store(),
    )


def check_and_reindex(full_rebuild: bool = False) -> str | None:
    """Check for a reindex trigger file and reindex if found.

    The daily sync writes ``data/.reindex_needed`` instead of touching stores
    directly.  This function is called by the UI before each query so the
    single owner process (the UI) performs the actual reindex.

    Uses incremental indexing: only re-chunks and embeds new/modified files,
    and removes chunks for deleted files. First run (empty tracker) behaves
    like a full rebuild.

    Args:
        full_rebuild: If True, clear the tracker and do a full reindex.

    Returns a status message, or None if no reindex was needed.
    """
    data_path = get_data_path()
    trigger = data_path / ".reindex_needed"
    if not trigger.exists():
        return None

    vault_path_str = trigger.read_text().strip()
    trigger.unlink()

    from secondbrain.indexing.chunker import Chunker
    from secondbrain.vault.connector import VaultConnector

    vault_path = Path(vault_path_str)
    if not vault_path.exists():
        logger.error("Reindex trigger vault path does not exist: %s", vault_path)
        return None

    logger.info("Reindex triggered for %s", vault_path)
    connector = VaultConnector(vault_path)
    chunker = Chunker()
    embedder = get_embedder()
    vector_store = get_vector_store()
    lexical_store = get_lexical_store()
    tracker = get_index_tracker()

    if full_rebuild:
        tracker.clear()

    # Step 1: Get file metadata (mtimes + hashes)
    vault_files = connector.get_file_metadata()
    if not vault_files:
        logger.info("Reindex: 0 notes found")
        return "Reindex: 0 notes"

    # Step 2: Classify changes
    new_files, modified_files, deleted_files, unchanged_files = tracker.classify_changes(
        vault_files
    )

    # Step 3: Delete chunks for deleted + modified files
    for file_path in deleted_files + modified_files:
        vector_store.delete_by_note_path(file_path)
        lexical_store.delete_by_note_path(file_path)
        if file_path in deleted_files:
            tracker.remove_file(file_path)

    # Step 4: Re-chunk and embed new + modified files
    files_to_index = new_files + modified_files
    total_chunks = 0
    for file_path in files_to_index:
        try:
            note = connector.read_note(Path(file_path))
        except Exception as e:
            logger.warning("Error reading %s: %s", file_path, e)
            continue

        chunks = chunker.chunk_note(note)
        if chunks:
            note_folder, note_date = extract_note_metadata(note.path, note.frontmatter)
            for c in chunks:
                c.note_folder = note_folder
                c.note_date = note_date
            texts = [build_embedding_text(c) for c in chunks]
            embeddings = embedder.embed(texts)
            vector_store.add_chunks(chunks, embeddings)
            lexical_store.add_chunks(chunks)

        # Step 5: Update tracker
        mtime, content_hash = vault_files[file_path]
        tracker.mark_indexed(file_path, content_hash, mtime, len(chunks))
        total_chunks += len(chunks)

    # Step 6: Store embedding model metadata
    vector_store.set_stored_model(embedder.model_name)

    # Step 7: Write epoch file for multi-process coordination
    epoch_file = data_path / ".reindex_epoch"
    epoch_file.write_text(str(Path(vault_path_str)))

    msg = (
        f"Incremental reindex: {len(new_files)} new, {len(modified_files)} modified, "
        f"{len(deleted_files)} deleted, {len(unchanged_files)} unchanged "
        f"({total_chunks} chunks indexed)"
    )
    logger.info(msg)
    return msg
