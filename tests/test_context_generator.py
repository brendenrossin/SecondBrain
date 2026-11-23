"""Tests for contextual retrieval — context blurb generation and integration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest

from secondbrain.config import Settings
from secondbrain.indexing.context import ContextGenerator
from secondbrain.indexing.embedder import build_embedding_text
from secondbrain.models import Chunk
from secondbrain.stores.lexical import LexicalStore


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
    source_path = Path(__file__).parent.parent / "src" / "secondbrain" / "api" / "index.py"
    source = source_path.read_text()
    assert "ContextGenerator" in source, "index.py must use ContextGenerator"
    assert "generate_blurbs" in source, "index.py must call generate_blurbs"
    assert "context_blurb" in source, "index.py must set context_blurb on chunks"


# --- Spec 007: prompt-cached document prefix -------------------------------------------


def _response(text="blurb", input_tokens=100, output_tokens=20, write=0, read=0):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    resp.usage.cache_creation_input_tokens = write
    resp.usage.cache_read_input_tokens = read
    return resp


def _generator(mock_client, usage_store=None):
    with patch("secondbrain.indexing.context.Anthropic", return_value=mock_client):
        return ContextGenerator(api_key="test-key", usage_store=usage_store)


def test_document_is_a_cached_block_before_the_chunk():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _response()
    gen = _generator(mock_client)

    gen.generate_blurbs("Spec", "DOC BODY", [_make_chunk("CHUNK BODY")])

    kwargs = mock_client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert kwargs["system"].startswith("You are a context annotation assistant")
    (message,) = kwargs["messages"]
    assert message["role"] == "user"
    doc_block, chunk_block = message["content"]
    assert doc_block == {
        "type": "text",
        "text": '<document title="Spec">\nDOC BODY\n</document>',
        "cache_control": {"type": "ephemeral"},
    }
    assert chunk_block == {
        "type": "text",
        "text": "<chunk>\nCHUNK BODY\n</chunk>\n\n"
        "Write a 1-2 sentence context blurb for this chunk.",
    }


def test_every_chunk_sends_an_identical_prefix():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [_response(f"b{i}") for i in range(3)]
    gen = _generator(mock_client)

    gen.generate_blurbs("Note", "full doc", [_make_chunk(f"chunk {i}") for i in range(3)])

    calls = [c.kwargs for c in mock_client.messages.create.call_args_list]
    assert len(calls) == 3
    assert len({c["system"] for c in calls}) == 1
    prefixes = [c["messages"][0]["content"][0] for c in calls]
    assert all(p == prefixes[0] for p in prefixes)
    tails = [c["messages"][0]["content"][1]["text"] for c in calls]
    assert len(set(tails)) == 3


def test_cache_tokens_are_priced_and_logged():
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        _response(write=10_000),
        _response(read=10_000),
    ]
    usage_store = MagicMock()
    gen = _generator(mock_client, usage_store=usage_store)

    gen.generate_blurbs("Note", "doc", [_make_chunk("a"), _make_chunk("b")])

    first, second = (c.kwargs for c in usage_store.log_usage.call_args_list)
    assert first["cost_usd"] == pytest.approx(0.012700)
    assert second["cost_usd"] == pytest.approx(0.001200)
    assert first["input_tokens"] == 100 + 10_000
    assert second["input_tokens"] == 100 + 10_000
    assert first["metadata"] == {"cache_write_tokens": 10_000, "cache_read_tokens": 0}
    assert second["metadata"] == {"cache_write_tokens": 0, "cache_read_tokens": 10_000}


def test_missing_or_non_integer_cache_fields_count_as_zero():
    resp = MagicMock()
    resp.content = [MagicMock(text="blurb")]
    resp.usage.input_tokens = 1000
    resp.usage.output_tokens = 100
    # MagicMock auto-attributes: cache fields exist but are not ints
    mock_client = MagicMock()
    mock_client.messages.create.return_value = resp
    usage_store = MagicMock()
    gen = _generator(mock_client, usage_store=usage_store)

    gen.generate_blurbs("Note", "doc", [_make_chunk("a")])

    logged = usage_store.log_usage.call_args.kwargs
    assert logged["input_tokens"] == 1000
    assert logged["cost_usd"] == pytest.approx((1000 * 1.00 + 100 * 5.00) / 1e6)
    assert logged["metadata"] == {"cache_write_tokens": 0, "cache_read_tokens": 0}


def test_api_error_still_returns_empty_blurb():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.BadRequestError(
        "usage limit", response=httpx.Response(400, request=request), body=None
    )
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = error
    usage_store = MagicMock()
    gen = _generator(mock_client, usage_store=usage_store)

    blurbs = gen.generate_blurbs("Note", "doc", [_make_chunk("a")])

    assert blurbs == [""]
    logged = usage_store.log_usage.call_args.kwargs
    assert logged["status"] == "error"
    assert logged["input_tokens"] == 0 and logged["cost_usd"] == 0.0
