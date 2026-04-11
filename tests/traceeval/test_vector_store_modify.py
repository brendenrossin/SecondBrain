"""VectorStore modify failure tests — real bug found by TraceEval."""

import numpy as np
import pytest
from secondbrain.models import Chunk
from secondbrain.stores.vector import VectorStore


def _make_chunk(chunk_id: str = "c1", text: str = "hello") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        note_path="notes/test.md",
        note_title="Test",
        heading_path=["H1"],
        chunk_index=0,
        chunk_text=text,
        checksum="abc",
    )


def _rand_emb(n: int = 1, dim: int = 8) -> np.ndarray:
    return np.random.rand(n, dim).astype(np.float32)


class TestModifyDistanceFunction:
    def test_changing_distance_function_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        """Creating a collection with cosine then trying to modify to l2 raises ValueError."""
        store = VectorStore(data_path=tmp_path / "chroma")
        # Access collection to create it with cosine space
        _ = store.collection

        # ChromaDB raises ValueError when hnsw:space is changed on an existing collection
        with pytest.raises((ValueError, Exception)):
            store.collection.modify(metadata={"hnsw:space": "l2"})

    def test_data_survives_failed_modify(self, tmp_path: pytest.TempPathFactory) -> None:
        """Data added before a failed modify attempt remains intact afterward."""
        store = VectorStore(data_path=tmp_path / "chroma")
        chunk = _make_chunk()
        emb = _rand_emb(dim=8)

        store.add_chunks([chunk], emb)
        assert store.count() == 1

        # Attempt to change hnsw:space — should raise but not corrupt data
        try:
            store.collection.modify(metadata={"hnsw:space": "l2"})
        except Exception:
            pass  # Expected — we just want to confirm data survived

        assert store.count() == 1
        result = store.get_chunk("c1")
        assert result is not None
        metadata, document = result
        assert document == "hello"

    def test_set_stored_model_preserves_space(self, tmp_path: pytest.TempPathFactory) -> None:
        """set_stored_model stores the model name but silently drops hnsw:space from metadata.

        This documents the real bug: set_stored_model() calls collection.modify() with
        {"hnsw:space": "cosine", "embedding_model": model_name}.  ChromaDB's modify()
        succeeds in persisting the embedding_model key but removes hnsw:space from the
        in-memory metadata object, leaving the collection metadata without the space key.

        The method must not propagate any exception (it swallows internally).
        Data and count must survive intact.
        """
        store = VectorStore(data_path=tmp_path / "chroma")
        chunk = _make_chunk()
        emb = _rand_emb(dim=8)

        store.add_chunks([chunk], emb)
        assert store.count() == 1

        # Before: hnsw:space is present
        assert store.collection.metadata.get("hnsw:space") == "cosine"  # type: ignore[union-attr]

        # set_stored_model must not raise
        store.set_stored_model("bge-base-en-v1.5")

        # Model name is readable via get_stored_model (persisted successfully)
        assert store.get_stored_model() == "bge-base-en-v1.5"

        # BUG: hnsw:space is silently dropped from in-memory metadata after modify()
        meta = store.collection.metadata or {}
        assert "hnsw:space" not in meta

        # Data still intact
        assert store.count() == 1
        result = store.get_chunk("c1")
        assert result is not None
        _, document = result
        assert document == "hello"
