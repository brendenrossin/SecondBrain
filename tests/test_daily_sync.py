"""Tests for daily_sync metadata extraction."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from secondbrain.models import Note, NoteMetadata


def _make_note(path: str = "notes/test.md", content: str = "Test content") -> Note:
    return Note(path=path, title="Test", content=content, frontmatter={})


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


class TestExtractMetadataHashFix:
    """Verify that stored content_hash matches get_file_metadata() hash, not extractor hash."""

    @patch("secondbrain.scripts.daily_sync.get_settings")
    def test_stored_hash_matches_vault_hash(self, mock_settings, tmp_path: Path) -> None:
        """After extraction, stored hash should be the raw-file hash from get_file_metadata()."""
        mock_settings.return_value = MagicMock(data_path=str(tmp_path), metadata_db_name="meta.db")

        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        raw_bytes_hash = "raw_file_hash_abc123"
        extractor_hash = "extractor_content_hash_xyz"

        mock_connector = MagicMock()
        mock_connector.get_file_metadata.return_value = {
            "notes/test.md": (1234567890.0, raw_bytes_hash),
        }
        mock_connector.read_note.return_value = _make_note("notes/test.md", "Test content")

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _make_metadata(
            "notes/test.md", content_hash=extractor_hash
        )

        with (
            patch("secondbrain.vault.connector.VaultConnector", return_value=mock_connector),
            patch(
                "secondbrain.extraction.extractor.MetadataExtractor",
                return_value=mock_extractor,
            ),
            patch("secondbrain.scripts.llm_client.LLMClient"),
            patch("secondbrain.stores.usage.UsageStore"),
        ):
            from secondbrain.scripts.daily_sync import extract_metadata

            result = extract_metadata(vault_dir, tmp_path)

        assert "Extracted 1" in result

        # Verify the metadata was stored with the vault hash, not extractor hash
        from secondbrain.stores.metadata import MetadataStore

        store = MetadataStore(tmp_path / "meta.db")
        stored = store.get("notes/test.md")
        assert stored is not None
        assert stored.content_hash == raw_bytes_hash
        assert stored.content_hash != extractor_hash
        store.close()

    @patch("secondbrain.scripts.daily_sync.get_settings")
    def test_second_run_skips_unchanged(self, mock_settings, tmp_path: Path) -> None:
        """After first extraction, a second run with same hashes should skip all notes."""
        mock_settings.return_value = MagicMock(data_path=str(tmp_path), metadata_db_name="meta.db")

        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        raw_hash = "same_hash_both_runs"

        mock_connector = MagicMock()
        mock_connector.get_file_metadata.return_value = {
            "notes/test.md": (1234567890.0, raw_hash),
        }
        mock_connector.read_note.return_value = _make_note("notes/test.md")

        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = _make_metadata("notes/test.md", content_hash="wrong")

        with (
            patch("secondbrain.vault.connector.VaultConnector", return_value=mock_connector),
            patch(
                "secondbrain.extraction.extractor.MetadataExtractor",
                return_value=mock_extractor,
            ),
            patch("secondbrain.scripts.llm_client.LLMClient"),
            patch("secondbrain.stores.usage.UsageStore"),
        ):
            from secondbrain.scripts.daily_sync import extract_metadata

            # First run — should extract
            result1 = extract_metadata(vault_dir, tmp_path)
            assert "Extracted 1" in result1

            # Second run — same hashes, should skip
            result2 = extract_metadata(vault_dir, tmp_path)
            assert result2 == "All notes up to date"


class TestExtractMetadataUsageTracking:
    """Verify that extraction creates a UsageStore and passes it to LLMClient."""

    @patch("secondbrain.scripts.daily_sync.get_settings")
    def test_usage_store_created_with_extraction_type(self, mock_settings, tmp_path: Path) -> None:
        mock_settings.return_value = MagicMock(data_path=str(tmp_path), metadata_db_name="meta.db")

        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        mock_connector = MagicMock()
        mock_connector.get_file_metadata.return_value = {}

        mock_llm_cls = MagicMock()
        mock_usage_cls = MagicMock()

        with (
            patch("secondbrain.vault.connector.VaultConnector", return_value=mock_connector),
            patch("secondbrain.extraction.extractor.MetadataExtractor"),
            patch("secondbrain.scripts.llm_client.LLMClient", mock_llm_cls),
            patch("secondbrain.stores.usage.UsageStore", mock_usage_cls),
        ):
            from secondbrain.scripts.daily_sync import extract_metadata

            extract_metadata(vault_dir, tmp_path)

        # Verify UsageStore was created
        mock_usage_cls.assert_called_once_with(tmp_path / "usage.db")

        # Verify LLMClient was created with usage_store and usage_type="extraction"
        mock_llm_cls.assert_called_once()
        call_kwargs = mock_llm_cls.call_args
        assert call_kwargs.kwargs.get("usage_type") == "extraction"
        assert call_kwargs.kwargs.get("usage_store") == mock_usage_cls.return_value
