"""Tests for the quick capture API endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from secondbrain.main import app
from secondbrain.models import NoteMetadata
from secondbrain.retrieval.hybrid import RetrievalCandidate


@pytest.fixture()
def client():
    return TestClient(app)


class TestCapture:
    """Tests for POST /api/v1/capture."""

    def test_capture_success(self, client, tmp_path):
        """Captures text and writes a file to Inbox/."""
        with patch("secondbrain.api.capture.get_settings") as mock_settings:
            mock_settings.return_value.vault_path = tmp_path
            res = client.post(
                "/api/v1/capture",
                json={"text": "Buy groceries tomorrow"},
            )

        assert res.status_code == 200
        data = res.json()
        assert data["filename"].startswith("capture_")
        assert data["filename"].endswith(".md")
        assert "Inbox" in data["message"]

        # Verify the file was actually written
        inbox = tmp_path / "Inbox"
        files = list(inbox.glob("*.md"))
        assert len(files) == 1
        assert files[0].read_text(encoding="utf-8") == "Buy groceries tomorrow"

    def test_capture_creates_inbox_dir(self, client, tmp_path):
        """Creates the Inbox directory if it doesn't exist."""
        with patch("secondbrain.api.capture.get_settings") as mock_settings:
            mock_settings.return_value.vault_path = tmp_path
            res = client.post(
                "/api/v1/capture",
                json={"text": "Hello world"},
            )

        assert res.status_code == 200
        assert (tmp_path / "Inbox").is_dir()

    def test_capture_no_vault_path(self, client):
        """Returns 500 when vault path is not configured."""
        with patch("secondbrain.api.capture.get_settings") as mock_settings:
            mock_settings.return_value.vault_path = None
            res = client.post(
                "/api/v1/capture",
                json={"text": "Some text"},
            )

        assert res.status_code == 500
        assert "VAULT_PATH" in res.json()["detail"]

    def test_capture_empty_text(self, client):
        """Rejects empty text via Pydantic validation."""
        res = client.post("/api/v1/capture", json={"text": ""})
        assert res.status_code == 422

    def test_capture_missing_text(self, client):
        """Rejects missing text field."""
        res = client.post("/api/v1/capture", json={})
        assert res.status_code == 422

    def test_capture_text_too_long(self, client):
        """Rejects text exceeding max length."""
        res = client.post("/api/v1/capture", json={"text": "x" * 10001})
        assert res.status_code == 422

    def test_capture_returns_connections_field(self, client, tmp_path):
        with patch("secondbrain.api.capture.get_settings") as mock_settings:
            mock_settings.return_value.vault_path = tmp_path
            res = client.post("/api/v1/capture", json={"text": "some text"})

        assert res.status_code == 200
        assert "connections" in res.json()
        assert isinstance(res.json()["connections"], list)


def _make_retrieval_candidate(
    note_path: str,
    note_title: str,
    chunk_text: str = "Some chunk text for testing purposes",
    rrf_score: float = 0.5,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=f"{note_path}_0",
        note_path=note_path,
        note_title=note_title,
        heading_path=[],
        chunk_text=chunk_text,
        similarity_score=0.8,
        bm25_score=0.4,
        rrf_score=rrf_score,
    )


class TestCaptureConnections:
    def test_returns_connections_from_retrieval(self, client, tmp_path):
        candidates = [
            _make_retrieval_candidate("10_Notes/alpha.md", "Alpha Note", rrf_score=0.9),
            _make_retrieval_candidate("20_Projects/beta.md", "Beta Note", rrf_score=0.7),
        ]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = candidates
        mock_meta_store = MagicMock()
        mock_meta_store.get.return_value = None

        with (
            patch("secondbrain.api.capture.get_settings") as mock_settings,
            patch("secondbrain.api.capture.get_retriever", return_value=mock_retriever),
            patch("secondbrain.api.capture.get_metadata_store", return_value=mock_meta_store),
        ):
            mock_settings.return_value.vault_path = tmp_path
            res = client.post("/api/v1/capture", json={"text": "test query"})

        data = res.json()
        assert res.status_code == 200
        assert len(data["connections"]) == 2
        assert data["connections"][0]["note_title"] == "Alpha Note"
        assert data["connections"][0]["score"] == 0.9

    def test_deduplicates_by_note_path(self, client, tmp_path):
        candidates = [
            _make_retrieval_candidate("notes/a.md", "Note A", "chunk 1", rrf_score=0.6),
            _make_retrieval_candidate("notes/a.md", "Note A", "chunk 2", rrf_score=0.9),
        ]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = candidates
        mock_meta_store = MagicMock()
        mock_meta_store.get.return_value = None

        with (
            patch("secondbrain.api.capture.get_settings") as mock_settings,
            patch("secondbrain.api.capture.get_retriever", return_value=mock_retriever),
            patch("secondbrain.api.capture.get_metadata_store", return_value=mock_meta_store),
        ):
            mock_settings.return_value.vault_path = tmp_path
            res = client.post("/api/v1/capture", json={"text": "test"})

        data = res.json()
        assert len(data["connections"]) == 1
        assert data["connections"][0]["score"] == 0.9

    def test_caps_at_five_connections(self, client, tmp_path):
        candidates = [
            _make_retrieval_candidate(f"notes/{i}.md", f"Note {i}", rrf_score=0.9 - i * 0.1)
            for i in range(8)
        ]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = candidates
        mock_meta_store = MagicMock()
        mock_meta_store.get.return_value = None

        with (
            patch("secondbrain.api.capture.get_settings") as mock_settings,
            patch("secondbrain.api.capture.get_retriever", return_value=mock_retriever),
            patch("secondbrain.api.capture.get_metadata_store", return_value=mock_meta_store),
        ):
            mock_settings.return_value.vault_path = tmp_path
            res = client.post("/api/v1/capture", json={"text": "test"})

        assert len(res.json()["connections"]) == 5

    def test_uses_metadata_summary_as_snippet(self, client, tmp_path):
        candidates = [
            _make_retrieval_candidate("notes/a.md", "Note A", "raw chunk text", rrf_score=0.8),
        ]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = candidates

        meta = MagicMock(spec=NoteMetadata)
        meta.summary = "A nice summary of the note"
        mock_meta_store = MagicMock()
        mock_meta_store.get.return_value = meta

        with (
            patch("secondbrain.api.capture.get_settings") as mock_settings,
            patch("secondbrain.api.capture.get_retriever", return_value=mock_retriever),
            patch("secondbrain.api.capture.get_metadata_store", return_value=mock_meta_store),
        ):
            mock_settings.return_value.vault_path = tmp_path
            res = client.post("/api/v1/capture", json={"text": "test"})

        assert res.json()["connections"][0]["snippet"] == "A nice summary of the note"

    def test_falls_back_to_chunk_text_on_metadata_error(self, client, tmp_path):
        candidates = [
            _make_retrieval_candidate("notes/a.md", "Note A", "raw chunk text here", rrf_score=0.8),
        ]
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = candidates

        with (
            patch("secondbrain.api.capture.get_settings") as mock_settings,
            patch("secondbrain.api.capture.get_retriever", return_value=mock_retriever),
            patch("secondbrain.api.capture.get_metadata_store", side_effect=Exception("DB error")),
        ):
            mock_settings.return_value.vault_path = tmp_path
            res = client.post("/api/v1/capture", json={"text": "test"})

        data = res.json()
        assert res.status_code == 200
        assert len(data["connections"]) == 1
        assert data["connections"][0]["snippet"] == "raw chunk text here"

    def test_capture_succeeds_when_retriever_raises(self, client, tmp_path):
        with (
            patch("secondbrain.api.capture.get_settings") as mock_settings,
            patch(
                "secondbrain.api.capture.get_retriever",
                side_effect=Exception("Embedder not loaded"),
            ),
        ):
            mock_settings.return_value.vault_path = tmp_path
            res = client.post("/api/v1/capture", json={"text": "test"})

        data = res.json()
        assert res.status_code == 200
        assert data["connections"] == []
        assert data["filename"].startswith("capture_")
