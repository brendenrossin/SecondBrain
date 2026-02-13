"""Tests for Phase 8.7 operational hardening features."""

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from secondbrain.api.dependencies import get_settings
from secondbrain.main import app
from secondbrain.scripts.daily_sync import _rotate_logs


@pytest.fixture()
def client():
    return TestClient(app)


def _make_mock_settings(vault_path=None, data_path=None):
    """Create a mock Settings object for health endpoint testing."""
    mock = MagicMock()
    mock.vault_path = vault_path
    mock.data_path = data_path or Path("/tmp/test-data")
    return mock


# ── Health endpoint tests ──


class TestHealthEndpoint:
    def test_returns_ok_with_valid_vault(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["vault"] == "ok"
        assert "free_disk_gb" in data

    def test_returns_error_when_vault_none(self, client, tmp_path):
        mock_s = _make_mock_settings(vault_path=None, data_path=tmp_path)
        with patch("secondbrain.main.get_settings", return_value=mock_s):
            resp = client.get("/health")
            data = resp.json()
            assert data["status"] == "error"
            assert data["vault"] == "not configured or missing"

    def test_returns_error_when_vault_missing(self, client, tmp_path):
        mock_s = _make_mock_settings(vault_path=tmp_path / "nonexistent", data_path=tmp_path)
        with patch("secondbrain.main.get_settings", return_value=mock_s):
            resp = client.get("/health")
            data = resp.json()
            assert data["status"] == "error"
            assert data["vault"] == "not configured or missing"

    def test_warns_on_low_disk(self, client):
        with patch("secondbrain.main.shutil.disk_usage") as mock_du:
            mock_du.return_value = (100 * 1024**3, 99.5 * 1024**3, int(0.5 * 1024**3))
            resp = client.get("/health")
            data = resp.json()
            assert data["status"] == "warning"
            assert data["disk"] == "low"
            assert data["free_disk_gb"] == 0.5

    def test_sync_marker_missing(self, client, tmp_path):
        mock_s = _make_mock_settings(vault_path=tmp_path, data_path=tmp_path)
        with patch("secondbrain.main.get_settings", return_value=mock_s):
            resp = client.get("/health")
            data = resp.json()
            assert data["last_sync_hours_ago"] is None

    def test_sync_marker_recent(self, client, tmp_path):
        marker = tmp_path / ".sync_completed"
        marker.write_text("2026-02-13T06:00:00")
        mock_s = _make_mock_settings(vault_path=tmp_path, data_path=tmp_path)
        with patch("secondbrain.main.get_settings", return_value=mock_s):
            resp = client.get("/health")
            data = resp.json()
            assert data["last_sync_hours_ago"] is not None
            assert "sync" not in data  # not stale

    def test_sync_marker_stale(self, client, tmp_path):
        marker = tmp_path / ".sync_completed"
        marker.write_text("2026-02-11T06:00:00")
        old_time = time.time() - (26 * 3600)
        os.utime(marker, (old_time, old_time))
        mock_s = _make_mock_settings(vault_path=tmp_path, data_path=tmp_path)
        with patch("secondbrain.main.get_settings", return_value=mock_s):
            resp = client.get("/health")
            data = resp.json()
            assert data["sync"] == "stale"
            assert data["last_sync_hours_ago"] > 25


# ── Log rotation tests ──


class TestRotateLogs:
    def test_skips_nonexistent_files(self, tmp_path):
        _rotate_logs(tmp_path)
        assert not (tmp_path / "daily-sync.log.old").exists()

    def test_skips_files_under_threshold(self, tmp_path):
        log_file = tmp_path / "api.log"
        log_file.write_bytes(b"x" * 1024)  # 1 KB, under 10 MB
        _rotate_logs(tmp_path)
        assert log_file.exists()
        assert not (tmp_path / "api.log.old").exists()

    def test_rotates_file_over_threshold(self, tmp_path):
        log_file = tmp_path / "api.log"
        log_file.write_bytes(b"x" * int(10.1 * 1024 * 1024))
        _rotate_logs(tmp_path)
        assert not log_file.exists()
        assert (tmp_path / "api.log.old").exists()

    def test_replaces_existing_old_file(self, tmp_path):
        log_file = tmp_path / "api.log"
        log_file.write_bytes(b"x" * int(10.1 * 1024 * 1024))
        old_file = tmp_path / "api.log.old"
        old_file.write_text("previous rotation")
        _rotate_logs(tmp_path)
        assert not log_file.exists()
        assert old_file.exists()
        assert old_file.stat().st_size > 1024

    def test_rotates_queries_jsonl(self, tmp_path):
        log_file = tmp_path / "queries.jsonl"
        log_file.write_bytes(b"x" * int(10.1 * 1024 * 1024))
        _rotate_logs(tmp_path)
        assert not log_file.exists()
        assert (tmp_path / "queries.jsonl.old").exists()

    def test_custom_threshold(self, tmp_path):
        log_file = tmp_path / "api.log"
        log_file.write_bytes(b"x" * int(5.1 * 1024 * 1024))
        _rotate_logs(tmp_path, max_size_mb=5.0)
        assert not log_file.exists()
        assert (tmp_path / "api.log.old").exists()

    def test_mixed_files_only_rotates_large(self, tmp_path):
        small = tmp_path / "api.log"
        small.write_bytes(b"x" * 1024)
        big = tmp_path / "daily-sync.log"
        big.write_bytes(b"x" * int(10.1 * 1024 * 1024))
        _rotate_logs(tmp_path)
        assert small.exists()
        assert not big.exists()
        assert (tmp_path / "daily-sync.log.old").exists()


# ── Sync status endpoint tests ──


class TestSyncStatusEndpoint:
    @pytest.fixture(autouse=True)
    def _setup_data_path(self, tmp_path):
        settings = get_settings()
        self._original = settings.data_path
        settings.data_path = tmp_path
        self._tmp = tmp_path
        yield
        settings.data_path = self._original

    def test_unknown_when_no_markers(self, client):
        resp = client.get("/api/v1/admin/sync-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unknown"
        assert data["last_sync"] is None

    def test_ok_when_recent_completed(self, client):
        marker = self._tmp / ".sync_completed"
        marker.write_text("2026-02-13T08:00:00")
        resp = client.get("/api/v1/admin/sync-status")
        data = resp.json()
        assert data["status"] == "ok"
        assert data["last_sync"] == "2026-02-13T08:00:00"
        assert "hours_ago" in data

    def test_stale_when_old_completed(self, client):
        marker = self._tmp / ".sync_completed"
        marker.write_text("2026-02-11T06:00:00")
        old_time = time.time() - (26 * 3600)
        os.utime(marker, (old_time, old_time))
        resp = client.get("/api/v1/admin/sync-status")
        data = resp.json()
        assert data["status"] == "stale"
        assert data["hours_ago"] > 25

    def test_failed_when_failure_marker_newer(self, client):
        completed = self._tmp / ".sync_completed"
        completed.write_text("2026-02-13T06:00:00")
        old_time = time.time() - 7200
        os.utime(completed, (old_time, old_time))

        failed = self._tmp / ".sync_failed"
        failed.write_text("2026-02-13T07:00:00: Connection refused")
        resp = client.get("/api/v1/admin/sync-status")
        data = resp.json()
        assert data["status"] == "failed"
        assert "Connection refused" in data["error"]

    def test_ok_when_completed_newer_than_failed(self, client):
        failed = self._tmp / ".sync_failed"
        failed.write_text("2026-02-13T06:00:00: old error")
        old_time = time.time() - 7200
        os.utime(failed, (old_time, old_time))

        completed = self._tmp / ".sync_completed"
        completed.write_text("2026-02-13T07:00:00")
        resp = client.get("/api/v1/admin/sync-status")
        data = resp.json()
        assert data["status"] == "ok"

    def test_failed_only_marker(self, client):
        failed = self._tmp / ".sync_failed"
        failed.write_text("2026-02-13T07:00:00: timeout")
        resp = client.get("/api/v1/admin/sync-status")
        data = resp.json()
        assert data["status"] == "failed"
        assert "timeout" in data["error"]


# ── Reindex lock tests ──


class TestReindexLock:
    def test_no_trigger_returns_none(self, tmp_path):
        with patch("secondbrain.api.dependencies.get_data_path", return_value=tmp_path):
            from secondbrain.api.dependencies import check_and_reindex

            result = check_and_reindex()
            assert result is None

    def test_skips_when_lock_active(self, tmp_path):
        trigger = tmp_path / ".reindex_needed"
        trigger.write_text("/some/vault")
        lock = tmp_path / ".reindex_lock"
        lock.write_text("12345")

        with patch("secondbrain.api.dependencies.get_data_path", return_value=tmp_path):
            from secondbrain.api.dependencies import check_and_reindex

            result = check_and_reindex()
            assert result is None
            assert not trigger.exists()  # Trigger was consumed

    def test_removes_stale_lock(self, tmp_path):
        vault = tmp_path / "nosuchvault"  # Does not exist
        trigger = tmp_path / ".reindex_needed"
        trigger.write_text(str(vault))
        lock = tmp_path / ".reindex_lock"
        lock.write_text("99999")
        old_time = time.time() - 700  # 700s > 600s threshold
        os.utime(lock, (old_time, old_time))

        with patch("secondbrain.api.dependencies.get_data_path", return_value=tmp_path):
            from secondbrain.api.dependencies import check_and_reindex

            result = check_and_reindex()
            # Vault doesn't exist, so returns None
            assert result is None
            # Lock released by finally block
            assert not lock.exists()

    def test_lock_released_on_success(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        trigger = tmp_path / ".reindex_needed"
        trigger.write_text(str(vault))

        mock_connector = MagicMock()
        mock_connector.get_file_metadata.return_value = {}

        with (
            patch("secondbrain.api.dependencies.get_data_path", return_value=tmp_path),
            patch(
                "secondbrain.vault.connector.VaultConnector",
                return_value=mock_connector,
            ),
        ):
            from secondbrain.api.dependencies import check_and_reindex

            check_and_reindex()
            assert not (tmp_path / ".reindex_lock").exists()

    def test_lock_not_created_without_trigger(self, tmp_path):
        with patch("secondbrain.api.dependencies.get_data_path", return_value=tmp_path):
            from secondbrain.api.dependencies import check_and_reindex

            check_and_reindex()
            assert not (tmp_path / ".reindex_lock").exists()
