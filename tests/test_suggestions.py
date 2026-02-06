"""Tests for the suggestion engine module."""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from secondbrain.models import Entity, NoteMetadata
from secondbrain.stores.metadata import MetadataStore
from secondbrain.suggestions.engine import SuggestionEngine


def _make_metadata(
    note_path: str,
    key_phrases: list[str] | None = None,
    entities: list[Entity] | None = None,
) -> NoteMetadata:
    return NoteMetadata(
        note_path=note_path,
        summary=f"Summary of {note_path}",
        key_phrases=key_phrases or ["python"],
        entities=entities or [],
        dates=[],
        action_items=[],
        extracted_at="2025-01-01T00:00:00+00:00",
        content_hash="hash123",
        model_used="test-model",
    )


class TestSuggestionEngine:
    def _setup_engine(self, tmp_path: Path) -> tuple[SuggestionEngine, MetadataStore]:
        metadata_store = MetadataStore(tmp_path / "meta.db")
        mock_vector_store = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.zeros(384, dtype=np.float32)

        engine = SuggestionEngine(
            vector_store=mock_vector_store,
            metadata_store=metadata_store,
            embedder=mock_embedder,
        )
        return engine, metadata_store

    def test_suggest_returns_none_without_metadata(self, tmp_path: Path) -> None:
        engine, _store = self._setup_engine(tmp_path)
        result = engine.suggest("nonexistent.md")
        assert result is None

    def test_suggest_returns_related_notes(self, tmp_path: Path) -> None:
        engine, store = self._setup_engine(tmp_path)

        # Set up source and target metadata
        store.upsert(_make_metadata("source.md", key_phrases=["python", "testing"]))
        store.upsert(_make_metadata("related.md", key_phrases=["python", "coding"]))

        # Mock vector search to return the related note's chunks
        engine.vector_store.search.return_value = [
            ("chunk1", 0.85, {"note_path": "related.md"}, "Some text"),
            ("chunk2", 0.60, {"note_path": "other.md"}, "Other text"),
        ]

        result = engine.suggest("source.md")
        assert result is not None
        assert result.note_path == "source.md"
        assert len(result.related_notes) == 2
        assert result.related_notes[0].note_path == "related.md"
        assert result.related_notes[0].similarity_score == 0.85
        store.close()

    def test_suggest_excludes_self(self, tmp_path: Path) -> None:
        engine, store = self._setup_engine(tmp_path)
        store.upsert(_make_metadata("source.md"))

        engine.vector_store.search.return_value = [
            ("chunk1", 0.99, {"note_path": "source.md"}, "Self reference"),
            ("chunk2", 0.70, {"note_path": "other.md"}, "Other"),
        ]

        result = engine.suggest("source.md")
        assert result is not None
        # source.md should be excluded from related
        paths = [r.note_path for r in result.related_notes]
        assert "source.md" not in paths
        store.close()

    def test_suggest_shared_entities(self, tmp_path: Path) -> None:
        engine, store = self._setup_engine(tmp_path)
        store.upsert(_make_metadata(
            "source.md",
            entities=[Entity(text="Alice", entity_type="person", confidence=0.9)],
        ))
        store.upsert(_make_metadata(
            "target.md",
            entities=[Entity(text="Alice", entity_type="person", confidence=0.85)],
        ))

        engine.vector_store.search.return_value = [
            ("chunk1", 0.80, {"note_path": "target.md"}, "Text"),
        ]

        result = engine.suggest("source.md")
        assert result is not None
        assert len(result.related_notes) == 1
        assert "Alice" in result.related_notes[0].shared_entities
        store.close()

    def test_suggest_link_from_shared_entity(self, tmp_path: Path) -> None:
        engine, store = self._setup_engine(tmp_path)
        store.upsert(_make_metadata(
            "source.md",
            entities=[Entity(text="Alice", entity_type="person", confidence=0.9)],
        ))
        store.upsert(_make_metadata(
            "target.md",
            entities=[Entity(text="Alice", entity_type="person", confidence=0.85)],
        ))

        engine.vector_store.search.return_value = [
            ("chunk1", 0.80, {"note_path": "target.md"}, "Text"),
        ]

        result = engine.suggest("source.md")
        assert result is not None
        assert len(result.suggested_links) >= 1
        link = result.suggested_links[0]
        assert link.anchor_text == "Alice"
        store.close()

    def test_suggest_tags_from_related(self, tmp_path: Path) -> None:
        engine, store = self._setup_engine(tmp_path)
        store.upsert(_make_metadata("source.md", key_phrases=["python"]))
        store.upsert(_make_metadata("rel1.md", key_phrases=["python", "flask", "api"]))
        store.upsert(_make_metadata("rel2.md", key_phrases=["python", "flask", "web"]))

        engine.vector_store.search.return_value = [
            ("c1", 0.85, {"note_path": "rel1.md"}, "T"),
            ("c2", 0.80, {"note_path": "rel2.md"}, "T"),
        ]

        result = engine.suggest("source.md")
        assert result is not None
        tag_names = [t.tag for t in result.suggested_tags]
        # "flask" appears in both related notes, should be suggested
        assert "flask" in tag_names
        # "python" is already in source, should NOT be suggested
        assert "python" not in tag_names
        store.close()
