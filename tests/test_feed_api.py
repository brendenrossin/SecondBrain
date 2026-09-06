"""Tests for the feed API endpoints — flag gating, response shape, click recording."""

from contextlib import contextmanager

import pytest

from secondbrain.api.dependencies import get_settings
from secondbrain.feed.models import FeedItem
from secondbrain.stores.feed import FeedStore


@contextmanager
def override_feed_settings(*, enabled, data_path):
    """Temporarily point the cached settings at a throwaway feed db."""
    settings = get_settings()
    original = (settings.feed_enabled, settings.data_path)
    settings.feed_enabled = enabled
    settings.data_path = data_path
    try:
        yield settings
    finally:
        settings.feed_enabled, settings.data_path = original


def _seed(data_path, db_name, items):
    store = FeedStore(data_path / db_name)
    try:
        store.add_items(items)
        store.update_summaries([i for i in items if i.summary])
    finally:
        store.close()


def _item(url, title, type="ai", score=1.0, summary=None):
    return FeedItem(
        url=url,
        source_label="Src",
        type=type,
        title=title,
        snippet="body",
        score=score,
        summary=summary,
    )


@pytest.fixture
def seeded(tmp_path):
    """A feed db with one summarized AI item and one unsummarized sports item."""
    settings = get_settings()
    _seed(
        tmp_path,
        settings.feed_db_name,
        [
            _item("https://x/ai", "Agents ship", score=9.0, summary="hot take"),
            _item("https://x/nfl", "Padres win", type="sports", score=1.0),
        ],
    )
    return tmp_path


class TestFeedFlagGating:
    def test_disabled_returns_empty_feed(self, client, seeded):
        with override_feed_settings(enabled=False, data_path=seeded):
            body = client.get("/api/v1/feed").json()
        assert body == {"generated": False, "sections": [], "items": []}

    def test_disabled_does_not_touch_the_store(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "secondbrain.api.feed._fetch_recent",
            lambda _s: pytest.fail("store must not be read when feed_enabled=False"),
        )
        with override_feed_settings(enabled=False, data_path=tmp_path):
            assert client.get("/api/v1/feed").status_code == 200


class TestFeedShape:
    def test_returns_items_ranked_by_score(self, client, seeded):
        with override_feed_settings(enabled=True, data_path=seeded):
            body = client.get("/api/v1/feed").json()
        assert [i["title"] for i in body["items"]] == ["Agents ship", "Padres win"]
        assert body["items"][0]["snippet"] == "body"

    def test_sections_contain_only_summarized_items(self, client, seeded):
        with override_feed_settings(enabled=True, data_path=seeded):
            body = client.get("/api/v1/feed").json()
        assert body["generated"] is True
        assert [s["heading"] for s in body["sections"]] == ["AI"]
        assert body["sections"][0]["items"] == [
            {"url": "https://x/ai", "title": "Agents ship", "take": "hot take"}
        ]

    def test_generated_false_when_nothing_was_summarized(self, client, tmp_path):
        settings = get_settings()
        _seed(tmp_path, settings.feed_db_name, [_item("https://x/raw", "Unsummarized")])
        with override_feed_settings(enabled=True, data_path=tmp_path):
            body = client.get("/api/v1/feed").json()
        assert body["generated"] is False
        assert body["sections"] == []
        assert len(body["items"]) == 1

    def test_empty_store_returns_empty_lists(self, client, tmp_path):
        with override_feed_settings(enabled=True, data_path=tmp_path):
            body = client.get("/api/v1/feed").json()
        assert body == {"generated": False, "sections": [], "items": []}


class TestFeedClick:
    def test_click_returns_url_and_records_it(self, client, seeded):
        settings = get_settings()
        with override_feed_settings(enabled=True, data_path=seeded):
            item_id = client.get("/api/v1/feed").json()["items"][0]["id"]
            resp = client.post(f"/api/v1/feed/{item_id}/click")
            assert resp.status_code == 200
            assert resp.json() == {"url": "https://x/ai"}

        store = FeedStore(seeded / settings.feed_db_name)
        try:
            row = next(r for r in store.get_recent() if r["id"] == item_id)
        finally:
            store.close()
        assert row["clicked_at"] is not None

    def test_unknown_item_returns_404(self, client, seeded):
        with override_feed_settings(enabled=True, data_path=seeded):
            resp = client.post("/api/v1/feed/99999/click")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


def _seed_overviews(data_path, overviews):
    store = FeedStore(data_path / get_settings().feed_db_name)
    try:
        store.replace_section_overviews(overviews)
    finally:
        store.close()


class TestSectionOverviews:
    def test_overview_is_returned_on_the_matching_section(self, client, seeded):
        _seed_overviews(seeded, {"ai": "Agents everywhere today."})
        with override_feed_settings(enabled=True, data_path=seeded):
            body = client.get("/api/v1/feed").json()
        assert body["sections"][0]["overview"] == "Agents everywhere today."

    def test_overview_is_null_when_none_was_stored(self, client, seeded):
        with override_feed_settings(enabled=True, data_path=seeded):
            body = client.get("/api/v1/feed").json()
        assert body["sections"][0]["overview"] is None

    def test_blank_overview_is_normalized_to_null(self, client, seeded):
        _seed_overviews(seeded, {"ai": ""})
        with override_feed_settings(enabled=True, data_path=seeded):
            body = client.get("/api/v1/feed").json()
        assert body["sections"][0]["overview"] is None

    def test_overview_for_a_type_with_no_summarized_items_creates_no_section(self, client, seeded):
        # The sports item in `seeded` is unsummarized, so it earns no section.
        _seed_overviews(seeded, {"sports": "Orphaned sports overview."})
        with override_feed_settings(enabled=True, data_path=seeded):
            body = client.get("/api/v1/feed").json()
        assert [s["heading"] for s in body["sections"]] == ["AI"]
        assert body["sections"][0]["overview"] is None
