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
