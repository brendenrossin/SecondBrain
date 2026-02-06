"""Tests for the metadata store module."""

from pathlib import Path

from secondbrain.models import ActionItem, DateMention, Entity, NoteMetadata
from secondbrain.stores.metadata import MetadataStore


def _make_metadata(
    note_path: str = "notes/test.md",
    content_hash: str = "abc123",
    summary: str = "Test summary",
) -> NoteMetadata:
    return NoteMetadata(
        note_path=note_path,
        summary=summary,
        key_phrases=["python", "testing"],
        entities=[
            Entity(text="Alice", entity_type="person", confidence=0.9),
            Entity(text="Acme Corp", entity_type="org", confidence=0.8),
        ],
        dates=[
            DateMention(
                text="2025-01-15",
                normalized_date="2025-01-15",
                date_type="deadline",
                confidence=0.95,
            ),
        ],
        action_items=[
            ActionItem(text="Review the PR", confidence=0.85, priority="high"),
        ],
        extracted_at="2025-01-01T00:00:00+00:00",
        content_hash=content_hash,
        model_used="test-model",
    )


class TestUpsertAndGet:
    def test_upsert_and_get(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        meta = _make_metadata()
        store.upsert(meta)

        result = store.get("notes/test.md")
        assert result is not None
        assert result.summary == "Test summary"
        assert result.key_phrases == ["python", "testing"]
        assert len(result.entities) == 2
        assert result.entities[0].text == "Alice"
        assert len(result.dates) == 1
        assert result.dates[0].normalized_date == "2025-01-15"
        assert len(result.action_items) == 1
        assert result.action_items[0].priority == "high"
        store.close()

    def test_upsert_overwrites(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        store.upsert(_make_metadata(summary="first"))
        store.upsert(_make_metadata(summary="second"))

        result = store.get("notes/test.md")
        assert result is not None
        assert result.summary == "second"
        store.close()

    def test_get_missing(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        assert store.get("nonexistent.md") is None
        store.close()


class TestGetAll:
    def test_get_all(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        store.upsert(_make_metadata("a.md"))
        store.upsert(_make_metadata("b.md"))
        store.upsert(_make_metadata("c.md"))

        all_meta = store.get_all()
        assert len(all_meta) == 3
        paths = [m.note_path for m in all_meta]
        assert paths == ["a.md", "b.md", "c.md"]  # sorted by note_path
        store.close()


class TestDelete:
    def test_delete(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        store.upsert(_make_metadata("a.md"))
        store.upsert(_make_metadata("b.md"))

        store.delete("a.md")
        assert store.get("a.md") is None
        assert store.get("b.md") is not None
        store.close()


class TestGetStale:
    def test_new_notes_are_stale(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        # No metadata yet, so all notes are stale
        stale = store.get_stale({"a.md": "hash1", "b.md": "hash2"})
        assert sorted(stale) == ["a.md", "b.md"]
        store.close()

    def test_hash_mismatch_is_stale(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        store.upsert(_make_metadata("a.md", content_hash="old_hash"))

        stale = store.get_stale({"a.md": "new_hash"})
        assert stale == ["a.md"]
        store.close()

    def test_matching_hash_not_stale(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        store.upsert(_make_metadata("a.md", content_hash="hash1"))

        stale = store.get_stale({"a.md": "hash1"})
        assert stale == []
        store.close()


class TestCountAndClear:
    def test_count(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        assert store.count() == 0
        store.upsert(_make_metadata("a.md"))
        store.upsert(_make_metadata("b.md"))
        assert store.count() == 2
        store.close()

    def test_clear(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        store.upsert(_make_metadata("a.md"))
        store.upsert(_make_metadata("b.md"))
        store.clear()
        assert store.count() == 0
        store.close()


class TestReconnect:
    def test_reconnect_on_closed_connection(self, tmp_path: Path) -> None:
        store = MetadataStore(tmp_path / "meta.db")
        store.upsert(_make_metadata("a.md"))

        # Close connection behind store's back
        store._conn.close()

        # Should reconnect and succeed
        store.upsert(_make_metadata("b.md"))
        assert store.count() == 2
        store.close()
