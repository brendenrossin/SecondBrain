"""VectorStore CRUD tests — gap identified by TraceEval trace analysis."""

import numpy as np
import pytest
from secondbrain.models import Chunk
from secondbrain.stores.vector import VectorStore


def _make_chunk(chunk_id="c1", note_path="notes/test.md", text="hello world"):
    return Chunk(
        chunk_id=chunk_id,
        note_path=note_path,
        note_title="Test Note",
        heading_path=["H1"],
        chunk_index=0,
        chunk_text=text,
        checksum="abc123",
    )


def _rand_embeddings(n=1, dim=8):
    return np.random.rand(n, dim).astype(np.float32)


@pytest.fixture
def store(tmp_path):
    return VectorStore(data_path=tmp_path / "chroma")


class TestVectorStoreAdd:
    def test_add_and_count(self, store):
        chunk = _make_chunk()
        store.add_chunks([chunk], _rand_embeddings(1))
        assert store.count() == 1

    def test_add_multiple_chunks(self, store):
        chunks = [_make_chunk(chunk_id=f"c{i}", note_path=f"notes/note{i}.md") for i in range(3)]
        store.add_chunks(chunks, _rand_embeddings(3))
        assert store.count() == 3

    def test_add_empty_list_is_noop(self, store):
        store.add_chunks([], np.empty((0, 8), dtype=np.float32))
        assert store.count() == 0

    def test_upsert_replaces_existing(self, store):
        chunk_v1 = _make_chunk(chunk_id="c1", text="original text")
        store.add_chunks([chunk_v1], _rand_embeddings(1))

        chunk_v2 = _make_chunk(chunk_id="c1", text="updated text")
        store.add_chunks([chunk_v2], _rand_embeddings(1))

        assert store.count() == 1
        result = store.get_chunk("c1")
        assert result is not None
        _, document = result
        assert document == "updated text"


class TestVectorStoreGet:
    def test_get_existing_chunk(self, store):
        chunk = _make_chunk(chunk_id="c1", note_path="notes/test.md", text="hello world")
        store.add_chunks([chunk], _rand_embeddings(1))

        result = store.get_chunk("c1")
        assert result is not None
        metadata, document = result
        assert document == "hello world"
        assert metadata["note_path"] == "notes/test.md"
        assert metadata["note_title"] == "Test Note"

    def test_get_nonexistent_returns_none(self, store):
        result = store.get_chunk("does_not_exist")
        assert result is None


class TestVectorStoreSearch:
    def test_search_returns_results(self, store):
        embedding = _rand_embeddings(1)
        chunk = _make_chunk()
        store.add_chunks([chunk], embedding)

        results = store.search(embedding[0], top_k=5)
        assert len(results) == 1
        chunk_id, similarity, metadata, document = results[0]
        assert chunk_id == "c1"
        assert similarity > 0.99  # same vector should be near-perfect cosine similarity

    def test_search_empty_store(self, store):
        results = store.search(_rand_embeddings(1)[0], top_k=5)
        assert results == []

    def test_search_min_similarity_filters(self, store):
        embedding = _rand_embeddings(1)
        chunk = _make_chunk()
        store.add_chunks([chunk], embedding)

        # With a very high min_similarity threshold, expect filtering to work without error
        results = store.search(embedding[0], top_k=5, min_similarity=0.0)
        assert isinstance(results, list)

        results_filtered = store.search(embedding[0], top_k=5, min_similarity=2.0)
        assert results_filtered == []


class TestVectorStoreDelete:
    def test_delete_by_note_path(self, store):
        chunk_a = _make_chunk(chunk_id="ca", note_path="notes/a.md", text="note a")
        chunk_b = _make_chunk(chunk_id="cb", note_path="notes/b.md", text="note b")
        store.add_chunks([chunk_a, chunk_b], _rand_embeddings(2))
        assert store.count() == 2

        deleted = store.delete_by_note_path("notes/a.md")
        assert "ca" in deleted
        assert store.count() == 1
        assert store.get_chunk("ca") is None
        assert store.get_chunk("cb") is not None

    def test_delete_chunks_by_id(self, store):
        chunk_a = _make_chunk(chunk_id="ca", note_path="notes/a.md")
        chunk_b = _make_chunk(chunk_id="cb", note_path="notes/b.md")
        store.add_chunks([chunk_a, chunk_b], _rand_embeddings(2))
        assert store.count() == 2

        store.delete_chunks(["ca"])
        assert store.count() == 1
        assert store.get_chunk("ca") is None
        assert store.get_chunk("cb") is not None

    def test_delete_empty_list_is_noop(self, store):
        chunk = _make_chunk()
        store.add_chunks([chunk], _rand_embeddings(1))
        store.delete_chunks([])
        assert store.count() == 1

    def test_clear(self, store):
        chunk = _make_chunk()
        store.add_chunks([chunk], _rand_embeddings(1))
        assert store.count() == 1
        store.clear()
        assert store.count() == 0


class TestVectorStoreModelMetadata:
    def test_set_and_get_model(self, store):
        store.set_stored_model("bge-base-en-v1.5")
        assert store.get_stored_model() == "bge-base-en-v1.5"

    def test_get_model_returns_none_initially(self, store):
        # Force collection creation so metadata exists but is empty
        _ = store.collection
        assert store.get_stored_model() is None

    def test_check_model_mismatch_true(self, store):
        store.set_stored_model("model-A")
        assert store.check_model_mismatch("model-B") is True

    def test_check_model_mismatch_false(self, store):
        store.set_stored_model("model-A")
        assert store.check_model_mismatch("model-A") is False

    def test_check_model_no_metadata(self, store):
        # Fresh store with no embedding_model set should return False (not a mismatch)
        _ = store.collection
        assert store.check_model_mismatch("any-model") is False
