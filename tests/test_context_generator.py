"""Tests for contextual retrieval — context blurb generation and integration."""

from secondbrain.config import Settings
from secondbrain.models import Chunk


def test_chunk_has_context_blurb_field():
    chunk = Chunk(
        chunk_id="abc123",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Section"],
        chunk_index=0,
        chunk_text="some text",
        checksum="def456",
    )
    assert chunk.context_blurb is None


def test_chunk_accepts_context_blurb():
    chunk = Chunk(
        chunk_id="abc123",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Section"],
        chunk_index=0,
        chunk_text="some text",
        checksum="def456",
        context_blurb="This is context about the test note.",
    )
    assert chunk.context_blurb == "This is context about the test note."


def test_context_generation_enabled_by_default():
    settings = Settings(_env_file=None, vault_path="/tmp/fake")
    assert settings.context_generation_enabled is True


from secondbrain.indexing.embedder import build_embedding_text


def test_build_embedding_text_with_blurb():
    chunk = Chunk(
        chunk_id="abc123",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Recipes", "Dinner"],
        chunk_index=0,
        chunk_text="3 medium parsnips, peeled",
        checksum="def456",
        context_blurb="Ingredients for Parsnip Purée from a Valentine's Day dinner recipe.",
    )
    result = build_embedding_text(chunk)
    assert result.startswith("[Context: Ingredients for Parsnip Purée")
    assert "Recipes > Dinner" in result
    assert "3 medium parsnips, peeled" in result


def test_build_embedding_text_without_blurb():
    chunk = Chunk(
        chunk_id="abc123",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Recipes"],
        chunk_index=0,
        chunk_text="some text",
        checksum="def456",
    )
    result = build_embedding_text(chunk)
    assert not result.startswith("[Context:")
    assert result == "Recipes\nsome text"


import uuid
from unittest.mock import MagicMock, patch

from secondbrain.indexing.context import ContextGenerator


def _make_chunk(text: str, heading: str = "Section") -> Chunk:
    return Chunk(
        chunk_id="test123",
        note_path="10_Notes/Test.md",
        note_title="Test Note",
        heading_path=[heading],
        chunk_index=0,
        chunk_text=text,
        checksum="check123",
    )


def test_context_generator_returns_blurbs():
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="This chunk describes testing patterns.")]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 20

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("secondbrain.indexing.context.Anthropic", return_value=mock_client):
        gen = ContextGenerator(api_key="test-key")
        chunks = [_make_chunk("def test_foo(): pass")]
        blurbs = gen.generate_blurbs("Test Note", "# Test\ndef test_foo(): pass", chunks)

    assert len(blurbs) == 1
    assert blurbs[0] == "This chunk describes testing patterns."
    mock_client.messages.create.assert_called_once()


def test_context_generator_handles_api_error():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    with patch("secondbrain.indexing.context.Anthropic", return_value=mock_client):
        gen = ContextGenerator(api_key="test-key")
        chunks = [_make_chunk("some text")]
        blurbs = gen.generate_blurbs("Test", "# Test\nsome text", chunks)

    assert len(blurbs) == 1
    assert blurbs[0] == ""


def test_context_generator_multiple_chunks():
    responses = []
    for i in range(3):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=f"Context for chunk {i}.")]
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.output_tokens = 20
        responses.append(mock_resp)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = responses

    with patch("secondbrain.indexing.context.Anthropic", return_value=mock_client):
        gen = ContextGenerator(api_key="test-key")
        chunks = [_make_chunk(f"chunk {i}") for i in range(3)]
        blurbs = gen.generate_blurbs("Note", "full doc", chunks)

    assert len(blurbs) == 3
    assert blurbs[1] == "Context for chunk 1."


from secondbrain.stores.lexical import LexicalStore


def test_lexical_store_stores_context_blurb(tmp_path):
    store = LexicalStore(tmp_path / "test.db")
    chunk = Chunk(
        chunk_id="blurb_test_1",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Section"],
        chunk_index=0,
        chunk_text="some text",
        checksum="abc",
        context_blurb="This chunk is about testing.",
    )
    store.add_chunks([chunk])
    result = store.get_chunk("blurb_test_1")
    assert result is not None
    assert result["context_blurb"] == "This chunk is about testing."


def test_lexical_store_blurb_in_fts_search(tmp_path):
    store = LexicalStore(tmp_path / "test.db")
    chunk = Chunk(
        chunk_id="fts_blurb_1",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Section"],
        chunk_index=0,
        chunk_text="3 medium parsnips peeled",
        checksum="abc",
        context_blurb="Ingredients for Valentine dinner recipe",
    )
    store.add_chunks([chunk])
    results = store.search("Valentine")
    assert len(results) >= 1
    assert results[0][0] == "fts_blurb_1"


def test_vector_store_metadata_includes_blurb(tmp_path):
    """Verify that vector store add_chunks passes context_blurb in metadata."""
    import numpy as np

    from secondbrain.stores.vector import VectorStore

    store = VectorStore(tmp_path / "chroma")
    chunk = Chunk(
        chunk_id="vec_blurb_1",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Section"],
        chunk_index=0,
        chunk_text="some text",
        checksum="abc",
        context_blurb="Context about testing.",
    )
    embeddings = np.random.rand(1, 384).astype(np.float32)
    store.add_chunks([chunk], embeddings)

    results = store._collection.get(ids=["vec_blurb_1"], include=["metadatas"])
    assert results["metadatas"][0]["context_blurb"] == "Context about testing."


def test_indexing_pipeline_calls_context_generator():
    """Verify index.py source code wires ContextGenerator into the pipeline."""
    from pathlib import Path

    source_path = Path(__file__).parent.parent / "src" / "secondbrain" / "api" / "index.py"
    source = source_path.read_text()
    assert "ContextGenerator" in source, "index.py must use ContextGenerator"
    assert "generate_blurbs" in source, "index.py must call generate_blurbs"
    assert "context_blurb" in source, "index.py must set context_blurb on chunks"
