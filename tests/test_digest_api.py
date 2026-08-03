"""Tests for the digest API endpoint — route wiring and vault availability."""

from unittest.mock import patch

from tests.conftest import override_vault_path

_CLEAR_CACHE = patch("secondbrain.api.briefing._cache", {"data": None, "ts": 0.0})


class TestDigestAPIVaultChecks:
    @_CLEAR_CACHE
    def test_returns_503_when_vault_none(self, client):
        with override_vault_path(None):
            resp = client.get("/api/v1/digest")
            assert resp.status_code == 503
            assert "Vault path" in resp.json()["detail"]

    @_CLEAR_CACHE
    def test_returns_503_when_vault_missing(self, client, tmp_path):
        with override_vault_path(tmp_path / "nonexistent"):
            resp = client.get("/api/v1/digest")
            assert resp.status_code == 503


class TestDigestAPIShape:
    @_CLEAR_CACHE
    def test_happy_path_returns_digest_shape(self, client, tmp_path):
        with override_vault_path(tmp_path):
            resp = client.get("/api/v1/digest")
            assert resp.status_code == 200
            body = resp.json()
            assert set(body) == {"title", "body", "count"}
            assert isinstance(body["title"], str) and body["title"]
            assert isinstance(body["body"], str) and body["body"]
            assert isinstance(body["count"], int) and body["count"] >= 0
