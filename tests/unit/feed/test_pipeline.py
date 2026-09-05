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
