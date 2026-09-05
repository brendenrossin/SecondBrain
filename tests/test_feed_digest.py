"""Tests for feed counts folding into the briefing digest one-liner."""

from secondbrain.api.briefing import _build_digest, _feed_counts
from secondbrain.config import Settings
from secondbrain.feed.models import FeedItem
from secondbrain.models import BriefingResponse
from secondbrain.stores.feed import FeedStore


def _briefing(**kw):
    base = {
        "today": "2026-08-04",
        "today_display": "Mon",
        "overdue_tasks": [],
        "due_today_tasks": [],
        "aging_followups": [],
        "yesterday_context": None,
        "today_context": None,
        "today_events": [],
        "total_open": 0,
        "feed_counts": {},
    }
    base.update(kw)
    return BriefingResponse(**base)


class TestDigestWithFeed:
    def test_feed_counts_fold_into_body_and_count(self):
        d = _build_digest(_briefing(feed_counts={"ai": 5, "sports": 3}))
        assert d.count == 8
        assert "5 AI updates" in d.body
        assert "3 sports" in d.body

    def test_no_feed_no_tasks_is_all_clear(self):
        d = _build_digest(_briefing(feed_counts={}))
        assert d.count == 0
        assert "All clear" in d.body

    def test_singular_ai_update(self):
        d = _build_digest(_briefing(feed_counts={"ai": 1}))
        assert "1 AI update" in d.body
        assert "updates" not in d.body

    def test_feed_alone_is_enough_to_break_all_clear(self):
        """The feed is a reason to open the app even with an empty task list."""
        d = _build_digest(_briefing(feed_counts={"ai": 2}))
        assert d.count == 2
        assert "All clear" not in d.body

    def test_tasks_precede_feed_in_the_body(self):
        d = _build_digest(_briefing(overdue_tasks=[], feed_counts={"ai": 1}))
        assert d.body == "1 AI update"

    def test_unknown_feed_type_gets_a_catch_all_segment(self):
        """count > 0 must never yield an empty push body."""
        d = _build_digest(_briefing(feed_counts={"general": 4}))
        assert d.count == 4
        assert d.body == "4 more"

    def test_every_nonzero_count_produces_a_nonempty_body(self):
        for counts in ({"ai": 1}, {"sports": 1}, {"general": 1}, {"ai": 1, "general": 2}):
            d = _build_digest(_briefing(feed_counts=counts))
            assert d.count > 0 and d.body.strip()


class TestFeedCountsLookup:
    def test_returns_empty_when_disabled(self, tmp_path):
        assert _feed_counts(Settings(feed_enabled=False, data_path=tmp_path)) == {}

    def test_counts_only_summarized_items_by_type(self, tmp_path):
        settings = Settings(feed_enabled=True, data_path=tmp_path, feed_top_n=10)
        store = FeedStore(tmp_path / settings.feed_db_name)
        items = [
            FeedItem(url="a", source_label="s", type="ai", title="a", snippet="", summary="t"),
            FeedItem(url="b", source_label="s", type="ai", title="b", snippet="", summary="t"),
            FeedItem(url="c", source_label="s", type="sports", title="c", snippet="", summary="t"),
            FeedItem(url="d", source_label="s", type="ai", title="d", snippet=""),  # no summary
        ]
        store.add_items(items)
        store.update_summaries(items)
        store.close()
        assert _feed_counts(settings) == {"ai": 2, "sports": 1}

    def test_missing_db_degrades_to_empty(self, tmp_path):
        settings = Settings(feed_enabled=True, data_path=tmp_path / "nope", feed_top_n=10)
        assert _feed_counts(settings) == {}
