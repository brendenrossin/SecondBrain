"""Tests for health endpoint."""

from httpx import ASGITransport, AsyncClient

from secondbrain.main import app


async def test_health_returns_ok():
    """Test that /health returns status ok."""
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
