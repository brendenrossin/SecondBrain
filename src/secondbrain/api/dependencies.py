"""FastAPI dependency injection for shared resources."""

from functools import lru_cache
from pathlib import Path

from secondbrain.config import Settings
from secondbrain.indexing.embedder import Embedder
from secondbrain.logging.query_logger import QueryLogger
from secondbrain.retrieval.hybrid import HybridRetriever
from secondbrain.retrieval.reranker import LLMReranker
from secondbrain.stores.conversation import ConversationStore
from secondbrain.stores.lexical import LexicalStore
from secondbrain.stores.vector import VectorStore
from secondbrain.synthesis.answerer import Answerer


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
    """Get cached embedder instance."""
    settings = get_settings()
    return Embedder(model_name=settings.embedding_model)


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
def get_retriever() -> HybridRetriever:
    """Get cached hybrid retriever instance."""
    return HybridRetriever(
        vector_store=get_vector_store(),
        lexical_store=get_lexical_store(),
        embedder=get_embedder(),
    )


@lru_cache
def get_reranker() -> LLMReranker:
    """Get cached reranker instance."""
    settings = get_settings()
    return LLMReranker(model=settings.rerank_model, api_key=settings.openai_api_key)


@lru_cache
def get_answerer() -> Answerer:
    """Get cached answerer instance."""
    settings = get_settings()
    return Answerer(model=settings.answer_model, api_key=settings.openai_api_key)
