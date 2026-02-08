"""Hybrid retrieval combining vector and lexical search."""

from dataclasses import dataclass
from typing import Any

from secondbrain.indexing.embedder import Embedder
from secondbrain.stores.lexical import LexicalStore
from secondbrain.stores.vector import VectorStore


@dataclass
class RetrievalCandidate:
    """A candidate chunk from retrieval."""

    chunk_id: str
    note_path: str
    note_title: str
    heading_path: list[str]
    chunk_text: str
    similarity_score: float
    bm25_score: float
    rrf_score: float
    note_folder: str = ""
    note_date: str = ""


class HybridRetriever:
    """Hybrid retriever combining vector and BM25 search using RRF."""

    def __init__(
        self,
        vector_store: VectorStore,
        lexical_store: LexicalStore,
        embedder: Embedder,
        k_vec: int = 30,
        k_lex: int = 50,
        rrf_k: int = 60,
        min_similarity: float = 0.3,
    ) -> None:
        """Initialize the hybrid retriever.

        Args:
            vector_store: Vector store for semantic search.
            lexical_store: Lexical store for BM25 search.
            embedder: Embedder for query embedding.
            k_vec: Number of vector search results.
            k_lex: Number of lexical search results.
            rrf_k: RRF constant (typically 60).
            min_similarity: Minimum similarity threshold for vector results.
        """
        self.vector_store = vector_store
        self.lexical_store = lexical_store
        self.embedder = embedder
        self.k_vec = k_vec
        self.k_lex = k_lex
        self.rrf_k = rrf_k
        self.min_similarity = min_similarity

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalCandidate]:
        """Retrieve candidates using hybrid search.

        Args:
            query: The search query.
            top_k: Number of final candidates to return.

        Returns:
            List of RetrievalCandidate objects, sorted by RRF score.
        """
        # Get query embedding
        query_embedding = self.embedder.embed_single(query)

        # Vector search
        vector_results = self.vector_store.search(
            query_embedding,
            top_k=self.k_vec,
            min_similarity=self.min_similarity,
        )

        # Lexical search
        lexical_results = self.lexical_store.search(query, top_k=self.k_lex)

        # Build lookup maps
        vector_scores: dict[str, float] = {}
        vector_data: dict[str, tuple[dict[str, Any], str]] = {}

        for chunk_id, similarity, metadata, document in vector_results:
            vector_scores[chunk_id] = similarity
            vector_data[chunk_id] = (metadata, document)

        lexical_scores: dict[str, float] = {}
        for chunk_id, bm25_score in lexical_results:
            lexical_scores[chunk_id] = bm25_score

        # Get all candidate IDs
        all_ids = set(vector_scores.keys()) | set(lexical_scores.keys())

        # Calculate RRF scores
        candidates: list[RetrievalCandidate] = []

        for chunk_id in all_ids:
            # Get ranks (1-indexed)
            vec_rank = self._get_rank(chunk_id, vector_results, key_idx=0)
            lex_rank = self._get_rank(chunk_id, lexical_results, key_idx=0)

            # RRF score
            rrf_score = 0.0
            if vec_rank is not None:
                rrf_score += 1.0 / (self.rrf_k + vec_rank)
            if lex_rank is not None:
                rrf_score += 1.0 / (self.rrf_k + lex_rank)

            # Get chunk data
            if chunk_id in vector_data:
                metadata, document = vector_data[chunk_id]
            else:
                # Fetch from lexical store
                chunk_data = self.lexical_store.get_chunk(chunk_id)
                if chunk_data:
                    metadata = chunk_data
                    document = chunk_data["chunk_text"]
                else:
                    continue

            # Parse heading path
            heading_path_str = metadata.get("heading_path", "")
            heading_path = heading_path_str.split("|") if heading_path_str else []

            candidates.append(
                RetrievalCandidate(
                    chunk_id=chunk_id,
                    note_path=metadata.get("note_path", ""),
                    note_title=metadata.get("note_title", ""),
                    heading_path=heading_path,
                    chunk_text=document,
                    similarity_score=vector_scores.get(chunk_id, 0.0),
                    bm25_score=lexical_scores.get(chunk_id, 0.0),
                    rrf_score=rrf_score,
                    note_folder=str(metadata.get("note_folder", "")),
                    note_date=str(metadata.get("note_date", "")),
                )
            )

        # Sort by RRF score and return top_k
        candidates.sort(key=lambda c: c.rrf_score, reverse=True)
        return candidates[:top_k]

    def _get_rank(self, chunk_id: str, results: list[Any], key_idx: int) -> int | None:
        """Get the 1-indexed rank of a chunk in results."""
        for i, result in enumerate(results):
            if result[key_idx] == chunk_id:
                return i + 1
        return None
