"""Tests for settings module and settings API endpoints."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from secondbrain.main import app
from secondbrain.settings import DEFAULT_SETTINGS, load_settings, save_settings

# ── Unit tests: load_settings / save_settings ──


class TestLoadSettings:
    def test_returns_defaults_when_file_missing(self, tmp_path):
        result = load_settings(tmp_path)
        assert result == DEFAULT_SETTINGS

    def test_writes_defaults_file_when_missing(self, tmp_path):
        load_settings(tmp_path)
        assert (tmp_path / "settings.json").exists()

    def test_reads_valid_json(self, tmp_path):
        custom = {"categories": [{"name": "Custom", "sub_projects": {}}]}
        (tmp_path / "settings.json").write_text(json.dumps(custom))
        result = load_settings(tmp_path)
        assert result == custom

    def test_returns_defaults_on_corrupt_json(self, tmp_path):
        (tmp_path / "settings.json").write_text("{invalid json!!")
        result = load_settings(tmp_path)
        assert result == DEFAULT_SETTINGS

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "dir"
        result = load_settings(nested)
        assert result == DEFAULT_SETTINGS
        assert (nested / "settings.json").exists()


class TestSaveSettings:
    def test_writes_valid_json(self, tmp_path):
        custom = {"categories": [{"name": "Test", "sub_projects": {"A": "desc"}}]}
        save_settings(tmp_path, custom)
        content = json.loads((tmp_path / "settings.json").read_text())
        assert content == custom

    def test_round_trip(self, tmp_path):
        custom = {"categories": [{"name": "RT", "sub_projects": {"X": "y"}}]}
        save_settings(tmp_path, custom)
        loaded = load_settings(tmp_path)
        assert loaded == custom

    def test_atomic_write_leaves_no_temp_files(self, tmp_path):
        save_settings(tmp_path, DEFAULT_SETTINGS)
        files = list(tmp_path.glob("*.tmp"))
        assert files == []

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "new" / "dir"
        save_settings(nested, DEFAULT_SETTINGS)
        assert (nested / "settings.json").exists()

    def test_overwrites_existing(self, tmp_path):
        save_settings(tmp_path, {"categories": [{"name": "Old", "sub_projects": {}}]})
        save_settings(tmp_path, {"categories": [{"name": "New", "sub_projects": {}}]})
        loaded = load_settings(tmp_path)
        assert loaded["categories"][0]["name"] == "New"


# ── API tests: GET/PUT /api/v1/settings/categories ──


@pytest.fixture()
def settings_dir(tmp_path):
    """Provide a temp data dir for settings tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture()
def settings_client(settings_dir):
    """TestClient with get_data_path patched to return settings_dir."""
    with patch("secondbrain.api.settings.get_data_path", return_value=settings_dir):
        yield TestClient(app)


class TestGetCategoriesAPI:
    def test_returns_defaults_on_fresh_install(self, settings_client):
        resp = settings_client.get("/api/v1/settings/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Work"
        assert data[1]["name"] == "Personal"

    def test_returns_saved_categories(self, settings_client, settings_dir):
        custom = {"categories": [{"name": "Custom", "sub_projects": {"A": "a desc"}}]}
        save_settings(settings_dir, custom)
        resp = settings_client.get("/api/v1/settings/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Custom"


class TestUpdateCategoriesAPI:
    def test_saves_and_returns_updated(self, settings_client, settings_dir):
        body = {"categories": [{"name": "NewCat", "sub_projects": {"Sub": "description"}}]}
        resp = settings_client.put("/api/v1/settings/categories", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["name"] == "NewCat"
        assert data[0]["sub_projects"]["Sub"] == "description"
        # Verify persisted
        loaded = load_settings(settings_dir)
        assert loaded["categories"][0]["name"] == "NewCat"

    def test_rejects_empty_category_name(self, settings_client):
        body = {"categories": [{"name": "  ", "sub_projects": {}}]}
        resp = settings_client.put("/api/v1/settings/categories", json=body)
        assert resp.status_code == 422

    def test_rejects_missing_name(self, settings_client):
        resp = settings_client.put(
            "/api/v1/settings/categories",
            json={"categories": [{"sub_projects": {}}]},
        )
        assert resp.status_code == 422

    def test_rejects_invalid_sub_projects_type(self, settings_client):
        resp = settings_client.put(
            "/api/v1/settings/categories",
            json={"categories": [{"name": "Bad", "sub_projects": "not a dict"}]},
        )
        assert resp.status_code == 422

    def test_allows_empty_sub_projects(self, settings_client):
        body = {"categories": [{"name": "Minimal", "sub_projects": {}}]}
        resp = settings_client.put("/api/v1/settings/categories", json=body)
        assert resp.status_code == 200
        assert resp.json()[0]["sub_projects"] == {}

    def test_multiple_categories(self, settings_client):
        body = {
            "categories": [
                {"name": "Work", "sub_projects": {}},
                {"name": "Personal", "sub_projects": {"Health": "wellness"}},
                {"name": "Side", "sub_projects": {}},
            ]
        }
        resp = settings_client.put("/api/v1/settings/categories", json=body)
        assert resp.status_code == 200
        assert len(resp.json()) == 3
