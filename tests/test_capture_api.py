"""Tests for the quick capture API endpoint."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from secondbrain.main import app


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
