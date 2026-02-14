"""Tests for the admin API endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from secondbrain.api.dependencies import (
    get_conversation_store,
    get_index_tracker,
    get_query_logger,
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

    app.dependency_overrides[get_usage_store] = lambda: mock_usage_store
    app.dependency_overrides[get_query_logger] = lambda: mock_query_logger
    app.dependency_overrides[get_conversation_store] = lambda: mock_conversation_store
    app.dependency_overrides[get_index_tracker] = lambda: mock_index_tracker

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
