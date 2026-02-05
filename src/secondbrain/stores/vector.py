"""ChromaDB vector store for semantic search."""

from pathlib import Path
from typing import Any

import chromadb
import numpy as np
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from numpy.typing import NDArray

from secondbrain.models import Chunk


class VectorStore:
    """Vector store using ChromaDB for semantic search."""

    def __init__(self, data_path: Path, collection_name: str = "chunks") -> None:
        """Initialize the vector store.

        Args:
            data_path: Path to store ChromaDB data.
            collection_name: Name of the collection.
        """
        self.data_path = data_path
        self.collection_name = collection_name
        self._client: ClientAPI | None = None
        self._collection: Collection | None = None

    @property
    def client(self) -> ClientAPI:
        """Lazy-load the ChromaDB client."""
        if self._client is None:
            self.data_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.data_path))
        return self._client

    @property
    def collection(self) -> Collection:
        """Get or create the collection."""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_chunks(
        self, chunks: list[Chunk], embeddings: NDArray[np.float32]
    ) -> None:
        """Add chunks with their embeddings to the store.

        Args:
            chunks: List of chunks to add.
            embeddings: Embeddings array with shape (len(chunks), embedding_dim).
        """
        if not chunks:
            return

        self.collection.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings.tolist(),
            metadatas=[
                {
                    "note_path": c.note_path,
                    "note_title": c.note_title,
                    "heading_path": "|".join(c.heading_path),
                    "chunk_index": c.chunk_index,
                    "checksum": c.checksum,
                }
                for c in chunks
            ],
            documents=[c.chunk_text for c in chunks],
        )

    def search(
        self,
        query_embedding: NDArray[np.float32],
        top_k: int = 30,
        min_similarity: float = 0.0,
    ) -> list[tuple[str, float, dict[str, Any], str]]:
        """Search for similar chunks.

        Args:
            query_embedding: Query embedding vector.
            top_k: Number of results to return.
            min_similarity: Minimum cosine similarity threshold.

        Returns:
            List of (chunk_id, similarity_score, metadata, document) tuples.
        """
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            include=["distances", "metadatas", "documents"],
        )

        # ChromaDB returns distances, convert to similarities
        # For cosine space, distance = 1 - similarity
        output: list[tuple[str, float, dict[str, Any], str]] = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results["distances"] else 0
                similarity = 1 - float(distance)

                if similarity >= min_similarity:
                    metadata: dict[str, Any] = dict(results["metadatas"][0][i]) if results["metadatas"] else {}
                    document = str(results["documents"][0][i]) if results["documents"] else ""
                    output.append((chunk_id, similarity, metadata, document))

        return output

    def get_chunk(self, chunk_id: str) -> tuple[dict[str, Any], str] | None:
        """Get a chunk by ID.

        Args:
            chunk_id: The chunk ID.

        Returns:
            Tuple of (metadata, document) or None if not found.
        """
        results = self.collection.get(
            ids=[chunk_id],
            include=["metadatas", "documents"],
        )
        if results["ids"] and results["metadatas"] and results["documents"]:
            return dict(results["metadatas"][0]), str(results["documents"][0])
        return None

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        """Delete chunks by ID."""
        if chunk_ids:
            self.collection.delete(ids=chunk_ids)

    def count(self) -> int:
        """Get the number of chunks in the store."""
        return self.collection.count()

    def clear(self) -> None:
        """Clear all chunks from the store."""
        self.client.delete_collection(self.collection_name)
        self._collection = None
