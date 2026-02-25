"""Tests for the admin API endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from secondbrain.api.dependencies import (
    get_conversation_store,
    get_index_tracker,
    get_query_logger,
    get_settings,
    get_usage_store,
)
from secondbrain.main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _mock_deps():
    """Mock all admin endpoint dependencies via FastAPI dependency overrides."""
    mock_usage_store = MagicMock()
    mock_usage_store.get_summary.return_value = {
        "total_cost": 0.05,
        "total_calls": 10,
        "by_provider": {
            "anthropic": {
                "cost": 0.04,
                "calls": 8,
                "input_tokens": 5000,
                "output_tokens": 2000,
            },
        },
        "by_usage_type": {
            "chat_rerank": {
                "cost": 0.02,
                "calls": 5,
                "input_tokens": 3000,
                "output_tokens": 1000,
            },
        },
    }
    mock_usage_store.get_daily_costs.return_value = [
        {
            "date": "2026-02-08",
            "cost_usd": 0.03,
            "calls": 6,
            "by_provider": {"anthropic": 0.03},
        },
    ]

    mock_query_logger = MagicMock()
    mock_query_logger.get_stats.return_value = {
        "total_queries": 25,
        "avg_latency_ms": 450.5,
    }

    mock_conversation_store = MagicMock()
    mock_conversation_store.count_conversations.return_value = 5
    mock_conversation_store.list_conversations.return_value = [
        {"conversation_id": f"conv-{i}"} for i in range(5)
    ]

    mock_index_tracker = MagicMock()
    mock_index_tracker.get_stats.return_value = {
        "file_count": 100,
        "total_chunks": 500,
        "last_indexed_at": "2026-02-08T12:00:00",
    }

    mock_settings = MagicMock()
    mock_settings.cost_alert_threshold = 1.00
    mock_settings.data_path = "/tmp/test"

    app.dependency_overrides[get_usage_store] = lambda: mock_usage_store
    app.dependency_overrides[get_query_logger] = lambda: mock_query_logger
    app.dependency_overrides[get_conversation_store] = lambda: mock_conversation_store
    app.dependency_overrides[get_index_tracker] = lambda: mock_index_tracker
    app.dependency_overrides[get_settings] = lambda: mock_settings

    yield

    app.dependency_overrides.clear()


class TestGetCosts:
    def test_default_period(self, client: TestClient):
        resp = client.get("/api/v1/admin/costs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "week"
        assert data["total_cost"] == 0.05
        assert data["total_calls"] == 10
        assert "anthropic" in data["by_provider"]
        assert "chat_rerank" in data["by_usage_type"]

    def test_month_period(self, client: TestClient):
        resp = client.get("/api/v1/admin/costs?period=month")
        assert resp.status_code == 200
        assert resp.json()["period"] == "month"

    def test_all_period(self, client: TestClient):
        resp = client.get("/api/v1/admin/costs?period=all")
        assert resp.status_code == 200
        assert resp.json()["period"] == "all"

    def test_invalid_period(self, client: TestClient):
        resp = client.get("/api/v1/admin/costs?period=invalid")
        assert resp.status_code == 422


class TestGetDailyCosts:
    def test_default_days(self, client: TestClient):
        resp = client.get("/api/v1/admin/costs/daily")
        assert resp.status_code == 200
        data = resp.json()
        assert data["days"] == 30
        assert len(data["daily"]) == 1
        assert data["daily"][0]["date"] == "2026-02-08"

    def test_custom_days(self, client: TestClient):
        resp = client.get("/api/v1/admin/costs/daily?days=7")
        assert resp.status_code == 200
        assert resp.json()["days"] == 7


class TestGetStats:
    def test_stats_response(self, client: TestClient):
        resp = client.get("/api/v1/admin/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_queries"] == 25
        assert data["avg_latency_ms"] == 450.5
        assert data["total_conversations"] == 5
        assert data["index_file_count"] == 100
        assert data["total_llm_calls"] == 10
        assert data["total_llm_cost"] == 0.05
        # Default mock returns date "2026-02-08" — not today, so today_cost=0
        assert data["today_cost"] == 0.0
        assert data["today_calls"] == 0
        assert data["cost_alert"] is None


class TestTodayCostFiltering:
    """Verify today's cost filters by today's date, not positional order."""

    def _make_usage_store(self, daily_costs: list[dict]) -> MagicMock:
        mock = MagicMock()
        mock.get_summary.return_value = {
            "total_cost": 5.00,
            "total_calls": 500,
            "by_provider": {},
            "by_usage_type": {},
        }
        mock.get_daily_costs.return_value = daily_costs
        return mock

    def test_picks_today_not_yesterday(self, client: TestClient):
        """When both yesterday and today exist, picks today's entry."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        mock = self._make_usage_store(
            [
                {"date": yesterday, "cost_usd": 0.50, "calls": 50, "by_provider": {}},
                {"date": today, "cost_usd": 0.10, "calls": 5, "by_provider": {}},
            ]
        )
        app.dependency_overrides[get_usage_store] = lambda: mock

        resp = client.get("/api/v1/admin/stats")
        data = resp.json()
        assert data["today_cost"] == 0.10
        assert data["today_calls"] == 5

    def test_yesterday_only_returns_zero(self, client: TestClient):
        """When only yesterday has data, today_cost should be 0."""
        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        mock = self._make_usage_store(
            [
                {"date": yesterday, "cost_usd": 0.50, "calls": 50, "by_provider": {}},
            ]
        )
        app.dependency_overrides[get_usage_store] = lambda: mock

        resp = client.get("/api/v1/admin/stats")
        data = resp.json()
        assert data["today_cost"] == 0.0
        assert data["today_calls"] == 0
        assert data["cost_alert"] is None

    def test_empty_data_returns_zero(self, client: TestClient):
        """When no daily data at all, today_cost should be 0."""
        mock = self._make_usage_store([])
        app.dependency_overrides[get_usage_store] = lambda: mock

        resp = client.get("/api/v1/admin/stats")
        data = resp.json()
        assert data["today_cost"] == 0.0
        assert data["today_calls"] == 0


class TestCostAlert:
    def test_high_cost_triggers_alert(self, client: TestClient):
        """Cost above threshold triggers an alert in stats response."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        mock_usage_store = MagicMock()
        mock_usage_store.get_summary.return_value = {
            "total_cost": 5.00,
            "total_calls": 500,
            "by_provider": {},
            "by_usage_type": {},
        }
        mock_usage_store.get_daily_costs.return_value = [
            {
                "date": today,
                "cost_usd": 2.50,
                "calls": 200,
                "by_provider": {"anthropic": 2.50},
            },
        ]
        app.dependency_overrides[get_usage_store] = lambda: mock_usage_store

        resp = client.get("/api/v1/admin/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["today_cost"] == 2.50
        assert data["today_calls"] == 200
        assert data["cost_alert"] is not None
        assert "$2.50" in data["cost_alert"]
        assert "$1.00" in data["cost_alert"]

    def test_alert_uses_today_not_yesterday(self, client: TestClient):
        """Cost alert is based on today's cost, not yesterday's high cost."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        mock_usage_store = MagicMock()
        mock_usage_store.get_summary.return_value = {
            "total_cost": 5.00,
            "total_calls": 500,
            "by_provider": {},
            "by_usage_type": {},
        }
        mock_usage_store.get_daily_costs.return_value = [
            {"date": yesterday, "cost_usd": 5.00, "calls": 500, "by_provider": {}},
            {"date": today, "cost_usd": 0.10, "calls": 5, "by_provider": {}},
        ]
        app.dependency_overrides[get_usage_store] = lambda: mock_usage_store

        resp = client.get("/api/v1/admin/stats")
        data = resp.json()
        # Yesterday was $5.00 (above threshold) but today is $0.10 — no alert
        assert data["today_cost"] == 0.10
        assert data["cost_alert"] is None

    def test_normal_cost_no_alert(self, client: TestClient):
        """Cost below threshold shows no alert."""
        resp = client.get("/api/v1/admin/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cost_alert"] is None


class TestGetStatsAnomalies:
    def test_stats_includes_anomalies(self, client: TestClient):
        resp = client.get("/api/v1/admin/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "anomalies" in data
        assert isinstance(data["anomalies"], list)

    def test_anomalies_from_usage_store(self, client: TestClient):
        mock_usage_store = MagicMock()
        mock_usage_store.get_summary.return_value = {
            "total_cost": 1.00,
            "total_calls": 100,
            "by_provider": {},
            "by_usage_type": {},
        }
        mock_usage_store.get_daily_costs.return_value = []
        mock_usage_store.get_anomalies.return_value = [
            {
                "type": "cost_spike",
                "severity": "critical",
                "message": "Today's cost is 5x the average",
                "details": {"today_cost": 0.50, "avg_daily_cost": 0.10},
            }
        ]
        app.dependency_overrides[get_usage_store] = lambda: mock_usage_store

        resp = client.get("/api/v1/admin/stats")
        data = resp.json()
        assert len(data["anomalies"]) == 1
        assert data["anomalies"][0]["type"] == "cost_spike"
        assert data["anomalies"][0]["severity"] == "critical"


class TestGetTraces:
    def test_traces_endpoint(self, client: TestClient):
        mock_usage_store = MagicMock()
        mock_usage_store.get_traces.return_value = [
            {
                "id": 1,
                "timestamp": "2026-02-24T10:00:00",
                "provider": "anthropic",
                "model": "claude-haiku-4-5",
                "usage_type": "chat_rerank",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.01,
                "trace_id": "abc123",
                "latency_ms": 42.5,
                "status": "ok",
                "error_message": None,
            }
        ]
        app.dependency_overrides[get_usage_store] = lambda: mock_usage_store

        resp = client.get("/api/v1/admin/traces")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["trace_id"] == "abc123"
        assert data[0]["latency_ms"] == 42.5

    def test_traces_with_filters(self, client: TestClient):
        mock_usage_store = MagicMock()
        mock_usage_store.get_traces.return_value = []
        app.dependency_overrides[get_usage_store] = lambda: mock_usage_store

        resp = client.get("/api/v1/admin/traces?usage_type=chat_rerank&status=error&limit=10")
        assert resp.status_code == 200
        mock_usage_store.get_traces.assert_called_once_with(
            limit=10,
            usage_type="chat_rerank",
            status="error",
            since=None,
        )

    def test_traces_limit_validation(self, client: TestClient):
        resp = client.get("/api/v1/admin/traces?limit=0")
        assert resp.status_code == 422

        resp = client.get("/api/v1/admin/traces?limit=201")
        assert resp.status_code == 422


class TestGetTraceGroup:
    def test_trace_group_endpoint(self, client: TestClient):
        mock_usage_store = MagicMock()
        mock_usage_store.get_trace_group.return_value = [
            {
                "id": 1,
                "timestamp": "2026-02-24T10:00:00",
                "provider": "anthropic",
                "model": "claude-haiku-4-5",
                "usage_type": "chat_rerank",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.01,
                "trace_id": "shared-trace",
                "latency_ms": 40.0,
                "status": "ok",
                "error_message": None,
            },
            {
                "id": 2,
                "timestamp": "2026-02-24T10:00:01",
                "provider": "anthropic",
                "model": "claude-haiku-4-5",
                "usage_type": "chat_answer",
                "input_tokens": 200,
                "output_tokens": 100,
                "cost_usd": 0.005,
                "trace_id": "shared-trace",
                "latency_ms": 1200.0,
                "status": "ok",
                "error_message": None,
            },
        ]
        app.dependency_overrides[get_usage_store] = lambda: mock_usage_store

        resp = client.get("/api/v1/admin/traces/shared-trace")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["usage_type"] == "chat_rerank"
        assert data[1]["usage_type"] == "chat_answer"
        mock_usage_store.get_trace_group.assert_called_once_with("shared-trace")

    def test_nonexistent_trace_returns_empty(self, client: TestClient):
        mock_usage_store = MagicMock()
        mock_usage_store.get_trace_group.return_value = []
        app.dependency_overrides[get_usage_store] = lambda: mock_usage_store

        resp = client.get("/api/v1/admin/traces/does-not-exist")
        assert resp.status_code == 200
        assert resp.json() == []
