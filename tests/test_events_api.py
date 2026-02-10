"""Tests for the events API endpoint."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from secondbrain.main import app
from secondbrain.scripts.event_parser import Event


@pytest.fixture
def client():
    return TestClient(app)


def _mock_events(_daily_dir, _start, _end):
    """Return mock events for testing."""
    return [
        Event(
            title="Standup",
            date="2026-02-10",
            time="9:00",
            end_date="",
            source_file="00_Daily/2026-02-10.md",
        ),
        Event(
            title="Dentist",
            date="2026-02-11",
            time="14:00",
            end_date="",
            source_file="00_Daily/2026-02-11.md",
        ),
        Event(
            title="Vacation",
            date="2026-02-12",
            time="",
            end_date="2026-02-14",
            source_file="00_Daily/2026-02-12.md",
        ),
    ]


class TestEventsAPI:
    @patch("secondbrain.api.events.get_events_in_range", side_effect=_mock_events)
    @patch("secondbrain.api.events._cache", {"data": None, "ts": 0.0, "key": ""})
    def test_list_events(self, _mock_events, client):
        resp = client.get("/api/v1/events?start=2026-02-10&end=2026-02-16")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert data[0]["title"] == "Standup"
        assert data[0]["time"] == "9:00"
        assert data[2]["end_date"] == "2026-02-14"

    @patch("secondbrain.api.events.get_events_in_range", return_value=[])
    @patch("secondbrain.api.events._cache", {"data": None, "ts": 0.0, "key": ""})
    def test_empty_events(self, _mock_events, client):
        resp = client.get("/api/v1/events?start=2026-03-01&end=2026-03-07")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_missing_params(self, client):
        resp = client.get("/api/v1/events")
        assert resp.status_code == 422  # validation error
