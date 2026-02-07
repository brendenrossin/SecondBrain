"""Embedding providers for document and query embedding."""

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# BGE models that benefit from a query prefix
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
_BGE_MODEL_PREFIXES = ("BAAI/bge-", "bge-")


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        """Embed a batch of documents."""
        ...

    def embed_query(self, text: str) -> NDArray[np.float32]:
        """Embed a single query (may apply query-specific prefixes)."""
        ...

    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        ...

    @property
    def model_name(self) -> str:
        """Model identifier string."""
        ...


class SentenceTransformerProvider:
    """Local embedding via sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: SentenceTransformer | None = None
        self._is_bge = any(model_name.startswith(p) for p in _BGE_MODEL_PREFIXES)

    @property
    def _st_model(self) -> "SentenceTransformer":
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        if not texts:
            return np.array([], dtype=np.float32)
        embeddings: Any = self._st_model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 10,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def embed_query(self, text: str) -> NDArray[np.float32]:
        if self._is_bge:
            text = _BGE_QUERY_PREFIX + text
        result: NDArray[np.float32] = self.embed([text])[0]
        return result

    @property
    def dimension(self) -> int:
        dim = self._st_model.get_sentence_embedding_dimension()
        return dim if dim is not None else 384

    @property
    def model_name(self) -> str:
        return self._model_name


class OpenAIEmbeddingProvider:
    """Embedding via OpenAI API (text-embedding-3-small/large)."""

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        api_key: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        self._model_name = model_name
        self._api_key = api_key
        self._dimensions = dimensions
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def _call_api(self, texts: list[str]) -> NDArray[np.float32]:
        client = self._get_client()
        kwargs: dict[str, Any] = {"model": self._model_name, "input": texts}
        if self._dimensions is not None:
            kwargs["dimensions"] = self._dimensions
        response = client.embeddings.create(**kwargs)
        embeddings = [item.embedding for item in response.data]
        return np.asarray(embeddings, dtype=np.float32)

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        if not texts:
            return np.array([], dtype=np.float32)
        # OpenAI API has a max batch size; chunk into batches of 2048
        all_embeddings: list[NDArray[np.float32]] = []
        batch_size = 2048
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            all_embeddings.append(self._call_api(batch))
        return np.concatenate(all_embeddings, axis=0)

    def embed_query(self, text: str) -> NDArray[np.float32]:
        result: NDArray[np.float32] = self._call_api([text])[0]
        return result

    @property
    def dimension(self) -> int:
        if self._dimensions is not None:
            return self._dimensions
        # Default dimensions for known models
        defaults = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return defaults.get(self._model_name, 1536)

    @property
    def model_name(self) -> str:
        return self._model_name


class Embedder:
    """Backwards-compatible wrapper around an EmbeddingProvider.

    Existing code that uses Embedder.embed() / embed_single() continues to work.
    New code should prefer using the provider directly via embed_query().
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        provider: EmbeddingProvider | None = None,
    ) -> None:
        if provider is not None:
            self._provider = provider
        else:
            self._provider = SentenceTransformerProvider(model_name)

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        return self._provider.embed(texts)

    def embed_single(self, text: str) -> NDArray[np.float32]:
        return self._provider.embed_query(text)

    def embed_query(self, text: str) -> NDArray[np.float32]:
        return self._provider.embed_query(text)

    @property
    def embedding_dim(self) -> int:
        return self._provider.dimension


@lru_cache(maxsize=1)
def get_embedder(model_name: str = "all-MiniLM-L6-v2") -> Embedder:
    """Get a cached embedder instance."""
    return Embedder(model_name)
