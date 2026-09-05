from datetime import UTC, datetime, timedelta

from secondbrain.config import Settings
from secondbrain.feed import pipeline as pipe
from secondbrain.feed.models import FeedItem, FeedSection, FeedSummary
from secondbrain.stores.feed import FeedStore


def _items(n=4, type="ai"):
    return [
        FeedItem(url=f"u{i}", source_label="s", type=type, title=f"agents story {i}", snippet="")
        for i in range(n)
    ]


def _settings(tmp_path, **kw):
    return Settings(feed_enabled=True, data_path=tmp_path, feed_top_n=3, feed_min_per_type=1, **kw)


def test_disabled_short_circuits(tmp_path):
    assert "disabled" in pipe.run_feed_pipeline(tmp_path, Settings(feed_enabled=False))


def test_disabled_never_fetches(tmp_path, monkeypatch):
    def boom(_sources):
        raise AssertionError("must not fetch when feed_enabled=False")

    monkeypatch.setattr(pipe, "fetch_all", boom)
    pipe.run_feed_pipeline(tmp_path, Settings(feed_enabled=False))


def test_pipeline_runs_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(pipe, "fetch_all", lambda _sources: _items(4))
    monkeypatch.setattr(
        pipe,
        "summarize_items",
        lambda _top, _settings, _usage: FeedSummary(sections=[], generated=False),
    )
    settings = _settings(tmp_path)
    result = pipe.run_feed_pipeline(tmp_path, settings)
    assert "4 fetched" in result and "3 summarized" in result
    assert len(FeedStore(tmp_path / settings.feed_db_name).get_recent()) == 4


def test_only_top_n_items_reach_the_llm(tmp_path, monkeypatch):
    seen = []

    def record_batch_size(top, _settings, _usage):
        seen.append(len(top))
        return FeedSummary(sections=[], generated=False)

    monkeypatch.setattr(pipe, "fetch_all", lambda _sources: _items(10))
    monkeypatch.setattr(pipe, "summarize_items", record_batch_size)
    pipe.run_feed_pipeline(tmp_path, _settings(tmp_path))
    assert seen == [3]  # exactly one call, capped at feed_top_n


def test_takes_are_written_back_to_the_store(tmp_path, monkeypatch):
    monkeypatch.setattr(pipe, "fetch_all", lambda _sources: _items(2))
    summary = FeedSummary(
        sections=[
            FeedSection(
                heading="AI", items=[{"url": "u0", "title": "agents story 0", "take": "hot"}]
            )
        ],
        generated=True,
    )
    monkeypatch.setattr(pipe, "summarize_items", lambda _t, _s, _u: summary)
    settings = _settings(tmp_path)
    assert "generated=True" in pipe.run_feed_pipeline(tmp_path, settings)
    rows = {r["url"]: r for r in FeedStore(tmp_path / settings.feed_db_name).get_recent()}
    assert rows["u0"]["summary"] == "hot"
    assert rows["u0"]["shown_at"] is not None
    assert rows["u1"]["summary"] is None  # no take returned for this one


def test_dedup_happens_before_ranking(tmp_path, monkeypatch):
    dupes = [
        FeedItem(
            url="https://x/1?utm_source=rss", source_label="s", type="ai", title="a", snippet=""
        ),
        FeedItem(url="https://x/1", source_label="s", type="ai", title="a", snippet=""),
    ]
    monkeypatch.setattr(pipe, "fetch_all", lambda _sources: dupes)
    monkeypatch.setattr(
        pipe, "summarize_items", lambda _t, _s, _u: FeedSummary(sections=[], generated=False)
    )
    result = pipe.run_feed_pipeline(tmp_path, _settings(tmp_path))
    assert "2 fetched, 1 unique" in result


class TestRefreshInterval:
    """The deployed cron runs `daily_sync all` hourly; without a guard that is
    24 LLM calls a day instead of one."""

    def test_is_due_false_within_the_window(self):
        recent = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        assert pipe._is_due(recent, 20) is False

    def test_is_due_true_past_the_window(self):
        old = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        assert pipe._is_due(old, 20) is True

    def test_is_due_true_for_unparseable_timestamp(self):
        """Better one extra refresh than a feed that silently never updates."""
        assert pipe._is_due("not-a-timestamp", 20) is True

    def test_is_due_treats_naive_timestamps_as_utc(self):
        naive = (datetime.now(UTC) - timedelta(hours=2)).replace(tzinfo=None).isoformat()
        assert pipe._is_due(naive, 20) is False

    def test_second_run_within_the_window_spends_nothing(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(pipe, "fetch_all", lambda _sources: _items(4))
        monkeypatch.setattr(
            pipe,
            "summarize_items",
            lambda _t, _s, _u: calls.append(1) or FeedSummary(sections=[], generated=False),
        )
        settings = _settings(tmp_path)
        first = pipe.run_feed_pipeline(tmp_path, settings)
        second = pipe.run_feed_pipeline(tmp_path, settings)
        assert "4 fetched" in first
        assert "skipped" in second.lower()
        assert len(calls) == 1  # the hourly re-run cost nothing

    def test_refresh_proceeds_once_the_window_has_passed(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(pipe, "fetch_all", lambda _sources: _items(4))
        monkeypatch.setattr(
            pipe,
            "summarize_items",
            lambda _t, _s, _u: calls.append(1) or FeedSummary(sections=[], generated=False),
        )
        settings = _settings(tmp_path)
        pipe.run_feed_pipeline(tmp_path, settings)
        store = FeedStore(tmp_path / settings.feed_db_name)
        stale = (datetime.now(UTC) - timedelta(hours=30)).isoformat()
        store.conn.execute("UPDATE feed_items SET fetched_at = ?", (stale,))
        store.conn.commit()
        store.close()
        assert "fetched" in pipe.run_feed_pipeline(tmp_path, settings)
        assert len(calls) == 2
