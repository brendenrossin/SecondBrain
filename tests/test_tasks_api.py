"""Tests for the tasks API endpoints — vault availability checks."""

from unittest.mock import patch

from tests.conftest import override_vault_path

_CLEAR_CACHE = patch("secondbrain.api.tasks._cache", {"data": None, "ts": 0.0})


class TestTasksAPIVaultChecks:
    @_CLEAR_CACHE
    def test_list_tasks_returns_503_when_vault_none(self, client):
        with override_vault_path(None):
            resp = client.get("/api/v1/tasks")
            assert resp.status_code == 503
            assert "Vault path" in resp.json()["detail"]

    @_CLEAR_CACHE
    def test_list_tasks_returns_503_when_vault_missing(self, client, tmp_path):
        with override_vault_path(tmp_path / "nonexistent"):
            resp = client.get("/api/v1/tasks")
            assert resp.status_code == 503

    @_CLEAR_CACHE
    def test_upcoming_returns_503_when_vault_none(self, client):
        with override_vault_path(None):
            resp = client.get("/api/v1/tasks/upcoming?days=7")
            assert resp.status_code == 503

    @_CLEAR_CACHE
    def test_categories_returns_503_when_vault_none(self, client):
        with override_vault_path(None):
            resp = client.get("/api/v1/tasks/categories")
            assert resp.status_code == 503

    def test_update_returns_503_when_vault_none(self, client):
        with override_vault_path(None):
            resp = client.patch(
                "/api/v1/tasks/update",
                json={
                    "text": "Test task",
                    "category": "Personal",
                    "sub_project": "General",
                    "status": "done",
                },
            )
            assert resp.status_code == 503
            assert "Vault path" in resp.json()["detail"]
