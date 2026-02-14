"""API latency benchmark tests — assert key endpoints respond within time budgets.

These tests use the real FastAPI app with mocked dependencies to measure actual
endpoint overhead (serialization, middleware, routing) without external I/O.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from secondbrain.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _mock_vault_path():
    """Ensure vault_path is set so endpoints don't 503."""
    with patch("secondbrain.config.get_settings") as mock_settings:
        settings = MagicMock()
        settings.vault_path = Path("/tmp/test-vault")
        settings.data_path = Path("/tmp/test-data")
        settings.debug = False
        mock_settings.return_value = settings
        yield


class TestHealthLatency:
    """Health endpoint should respond very fast."""

    def test_health_under_100ms(self, client):
        # Mock vault and disk checks
        with patch("secondbrain.main.get_settings") as mock_gs:
            settings = MagicMock()
            settings.vault_path = Path("/tmp")
            settings.data_path = Path("/tmp")
            mock_gs.return_value = settings

            start = time.perf_counter()
            response = client.get("/health")
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 100, f"Health endpoint took {elapsed_ms:.0f}ms (budget: 100ms)"


class TestTasksLatency:
    """Tasks endpoint should respond within 2s even with file scanning."""

    def test_tasks_under_2s(self, client):
        with (
            patch("secondbrain.api.tasks.scan_daily_notes", return_value=[]),
            patch("secondbrain.api.tasks.aggregate_tasks", return_value=[]),
        ):
            # Clear cache
            from secondbrain.api.tasks import _cache

            _cache["data"] = None

            start = time.perf_counter()
            response = client.get("/api/v1/tasks")
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 2000, f"Tasks endpoint took {elapsed_ms:.0f}ms (budget: 2000ms)"


class TestEventsLatency:
    """Events endpoint should respond within 2s."""

    def test_events_under_2s(self, client):
        with patch("secondbrain.api.events.get_events_in_range", return_value=[]):
            # Clear cache
            from secondbrain.api.events import _cache

            _cache["data"] = None

            start = time.perf_counter()
            response = client.get("/api/v1/events?start=2026-02-14&end=2026-02-14")
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 2000, f"Events endpoint took {elapsed_ms:.0f}ms (budget: 2000ms)"


class TestBriefingLatency:
    """Briefing endpoint should respond within 2s."""

    def test_briefing_under_2s(self, client):
        with (
            patch("secondbrain.api.briefing.scan_daily_notes", return_value=[]),
            patch("secondbrain.api.briefing.aggregate_tasks", return_value=[]),
            patch("secondbrain.api.briefing.find_recent_daily_context", return_value=None),
            patch("secondbrain.api.briefing.parse_daily_note_sections", return_value=None),
            patch("secondbrain.api.briefing.get_events_in_range", return_value=[]),
        ):
            # Clear cache
            from secondbrain.api.briefing import _cache

            _cache["data"] = None

            start = time.perf_counter()
            response = client.get("/api/v1/briefing")
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 2000, f"Briefing endpoint took {elapsed_ms:.0f}ms (budget: 2000ms)"


class TestAdminStatsLatency:
    """Admin stats endpoint should respond within 1s."""

    def test_admin_stats_under_1s(self, client):
        mock_usage = MagicMock()
        mock_usage.get_summary.return_value = {
            "total_cost": 0.0,
            "total_calls": 0,
            "by_provider": {},
            "by_usage_type": {},
        }
        mock_logger = MagicMock()
        mock_logger.get_stats.return_value = {"total_queries": 0, "avg_latency_ms": 0}
        mock_conv = MagicMock()
        mock_conv.count_conversations.return_value = 0
        mock_tracker = MagicMock()
        mock_tracker.get_stats.return_value = {"file_count": 0}

        with (
            patch("secondbrain.api.admin.get_usage_store", return_value=mock_usage),
            patch("secondbrain.api.admin.get_query_logger", return_value=mock_logger),
            patch("secondbrain.api.admin.get_conversation_store", return_value=mock_conv),
            patch("secondbrain.api.admin.get_index_tracker", return_value=mock_tracker),
        ):
            start = time.perf_counter()
            response = client.get("/api/v1/admin/stats")
            elapsed_ms = (time.perf_counter() - start) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 1000, f"Admin stats took {elapsed_ms:.0f}ms (budget: 1000ms)"
