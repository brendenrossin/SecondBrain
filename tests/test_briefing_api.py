"""Tests for the briefing API endpoint — vault availability checks."""

from unittest.mock import patch

from tests.conftest import override_vault_path

_CLEAR_CACHE = patch("secondbrain.api.briefing._cache", {"data": None, "ts": 0.0})


class TestBriefingAPIVaultChecks:
    @_CLEAR_CACHE
    def test_returns_503_when_vault_none(self, client):
        with override_vault_path(None):
            resp = client.get("/api/v1/briefing")
            assert resp.status_code == 503
            assert "Vault path" in resp.json()["detail"]

    @_CLEAR_CACHE
    def test_returns_503_when_vault_missing(self, client, tmp_path):
        with override_vault_path(tmp_path / "nonexistent"):
            resp = client.get("/api/v1/briefing")
            assert resp.status_code == 503
