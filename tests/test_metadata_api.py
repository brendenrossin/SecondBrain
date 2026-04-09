"""Tests for metadata API extraction hash consistency."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from secondbrain.api.dependencies import get_extractor, get_metadata_store, get_settings
from secondbrain.main import app
from secondbrain.models import Note, NoteMetadata
from secondbrain.stores.metadata import MetadataStore


def _make_metadata(note_path: str = "notes/test.md", content_hash: str = "abc") -> NoteMetadata:
    return NoteMetadata(
        note_path=note_path,
        summary="Summary",
        key_phrases=["test"],
        entities=[],
        dates=[],
        action_items=[],
        extracted_at="2026-01-01T00:00:00+00:00",
        content_hash=content_hash,
        model_used="test-model",
    )


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def vault_dir(tmp_path: Path) -> Path:
    """Create a temp vault with a test note."""
    vault = tmp_path / "vault"
    vault.mkdir()
    note_file = vault / "notes" / "test.md"
    note_file.parent.mkdir(parents=True)
    note_file.write_text("---\ntitle: Test\n---\nTest content")
    return vault


@pytest.fixture()
def metadata_db(tmp_path: Path) -> MetadataStore:
    return MetadataStore(tmp_path / "meta.db")


class TestBatchExtractionHashFix:
    """POST /extract (batch) stores the raw-bytes hash, not the extractor hash."""

    def test_stored_hash_matches_vault_hash(
        self, client: TestClient, vault_dir: Path, metadata_db: MetadataStore
    ) -> None:
        note_file = vault_dir / "notes" / "test.md"
        raw_bytes_hash = hashlib.sha1(note_file.read_bytes()).hexdigest()
        extractor_hash = "extractor_wrong_hash_xyz"

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _make_metadata(
            "notes/test.md", content_hash=extractor_hash
        )

        mock_settings = MagicMock()
        mock_settings.vault_path = str(vault_dir)

        # Mock VaultConnector to return our test note with matching hash
        mock_connector = MagicMock()
        mock_connector.get_file_metadata.return_value = {
            "notes/test.md": (1234567890.0, raw_bytes_hash),
        }
        mock_connector.read_note.return_value = Note(
            path="notes/test.md", title="Test", content="Test content", frontmatter={}
        )

        app.dependency_overrides[get_settings] = lambda: mock_settings
        app.dependency_overrides[get_extractor] = lambda: mock_extractor
        app.dependency_overrides[get_metadata_store] = lambda: metadata_db

        try:
            with patch("secondbrain.api.metadata.VaultConnector", return_value=mock_connector):
                resp = client.post("/api/v1/extract?force=true")

            assert resp.status_code == 200
            assert resp.json()["notes_extracted"] == 1

            stored = metadata_db.get("notes/test.md")
            assert stored is not None
            assert stored.content_hash == raw_bytes_hash
            assert stored.content_hash != extractor_hash
        finally:
            app.dependency_overrides.clear()
            metadata_db.close()


class TestSingleNoteExtractionHashFix:
    """POST /extract?note_path=... stores the raw-bytes hash, not the extractor hash."""

    def test_stored_hash_matches_vault_hash(
        self, client: TestClient, vault_dir: Path, metadata_db: MetadataStore
    ) -> None:
        note_file = vault_dir / "notes" / "test.md"
        raw_bytes_hash = hashlib.sha1(note_file.read_bytes()).hexdigest()
        extractor_hash = "extractor_wrong_hash_xyz"

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _make_metadata(
            "notes/test.md", content_hash=extractor_hash
        )

        mock_settings = MagicMock()
        mock_settings.vault_path = str(vault_dir)

        mock_connector = MagicMock()
        mock_connector.read_note.return_value = Note(
            path="notes/test.md", title="Test", content="Test content", frontmatter={}
        )

        app.dependency_overrides[get_settings] = lambda: mock_settings
        app.dependency_overrides[get_extractor] = lambda: mock_extractor
        app.dependency_overrides[get_metadata_store] = lambda: metadata_db

        try:
            with patch("secondbrain.api.metadata.VaultConnector", return_value=mock_connector):
                resp = client.post("/api/v1/extract?note_path=notes/test.md")

            assert resp.status_code == 200
            assert resp.json()["notes_extracted"] == 1

            stored = metadata_db.get("notes/test.md")
            assert stored is not None
            assert stored.content_hash == raw_bytes_hash
            assert stored.content_hash != extractor_hash
        finally:
            app.dependency_overrides.clear()
            metadata_db.close()
