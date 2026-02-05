"""Embedding generator using sentence-transformers."""

from functools import lru_cache
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class Embedder:
    """Generates embeddings using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Initialize the embedder.

        Args:
            model_name: The sentence-transformers model to use.
        """
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> "SentenceTransformer":
        """Lazy-load the model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> NDArray[np.float32]:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed.

        Returns:
            Numpy array of embeddings with shape (len(texts), embedding_dim).
        """
        if not texts:
            return np.array([], dtype=np.float32)

        embeddings: Any = self.model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 10,
        )
        return np.asarray(embeddings, dtype=np.float32)

    def embed_single(self, text: str) -> NDArray[np.float32]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            Numpy array of shape (embedding_dim,).
        """
        result: NDArray[np.float32] = self.embed([text])[0]
        return result

    @property
    def embedding_dim(self) -> int:
        """Get the embedding dimension."""
        dim = self.model.get_sentence_embedding_dimension()
        return dim if dim is not None else 384  # Default for MiniLM


@lru_cache(maxsize=1)
def get_embedder(model_name: str = "all-MiniLM-L6-v2") -> Embedder:
    """Get a cached embedder instance."""
    return Embedder(model_name)
