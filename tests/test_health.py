"""Tests for health endpoint."""

from unittest.mock import MagicMock, patch

from httpx import ASGITransport, AsyncClient

from secondbrain.main import app


async def test_health_returns_ok(tmp_path):
    """Test that /health returns status ok when vault exists."""
    mock_s = MagicMock()
    mock_s.vault_path = tmp_path
    mock_s.data_path = tmp_path
    with patch("secondbrain.main.get_settings", return_value=mock_s):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "vault" in data
    assert "free_disk_gb" in data
    assert "last_sync_hours_ago" in data


async def test_root_returns_project_info():
    """Test that / returns project information."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "SecondBrain"
    assert "version" in data
    assert "description" in data
