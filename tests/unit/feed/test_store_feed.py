from datetime import UTC, datetime, timedelta

from secondbrain.feed.models import FeedItem
from secondbrain.stores.feed import FeedStore


def _item(url, title="t", type="ai", score=1.0, summary=None):
    return FeedItem(
        url=url,
        source_label="s",
        type=type,
        title=title,
        snippet="snip",
        score=score,
        summary=summary,
    )


def _store(tmp_path):
    return FeedStore(tmp_path / "feed.db")


def test_add_dedups_on_url(tmp_path):
    store = _store(tmp_path)
    assert store.add_items([_item("https://x/1")]) == 1
    assert store.add_items([_item("https://x/1")]) == 0  # same url ignored
    assert len(store.get_recent()) == 1


def test_add_items_empty_is_a_noop(tmp_path):
    store = _store(tmp_path)
    assert store.add_items([]) == 0
    assert store.get_recent() == []


def test_add_items_counts_only_new_urls_in_mixed_batch(tmp_path):
    store = _store(tmp_path)
    store.add_items([_item("u1")])
    assert store.add_items([_item("u1"), _item("u2"), _item("u3")]) == 2


def test_get_recent_orders_by_score(tmp_path):
    store = _store(tmp_path)
    store.add_items([_item("u1", score=0.1), _item("u2", score=0.9)])
    assert store.get_recent()[0]["url"] == "u2"


def test_get_recent_honors_limit(tmp_path):
    store = _store(tmp_path)
    store.add_items([_item(f"u{i}", score=float(i)) for i in range(5)])
    assert len(store.get_recent(limit=2)) == 2


def test_update_summaries(tmp_path):
    store = _store(tmp_path)
    store.add_items([_item("u1")])
    store.update_summaries([_item("u1", score=2.0, summary="hot take")])
    row = store.get_recent()[0]
    assert row["summary"] == "hot take"
    assert row["score"] == 2.0


def test_update_summaries_skips_items_without_a_summary(tmp_path):
    store = _store(tmp_path)
    store.add_items([_item("u1", score=1.0)])
    store.update_summaries([_item("u1", score=9.0, summary=None)])
    row = store.get_recent()[0]
    assert row["summary"] is None
    assert row["score"] == 1.0  # score is only written alongside a summary


def test_mark_shown_keeps_first_timestamp(tmp_path):
    store = _store(tmp_path)
    store.add_items([_item("u1")])
    store.mark_shown(["u1"])
    first = store.get_recent()[0]["shown_at"]
    assert first is not None
    store.mark_shown(["u1"])
    assert store.get_recent()[0]["shown_at"] == first


def test_mark_clicked_returns_url(tmp_path):
    store = _store(tmp_path)
    store.add_items([_item("https://x/click")])
    row_id = store.get_recent()[0]["id"]
    assert store.mark_clicked(row_id) == "https://x/click"
    assert store.get_recent()[0]["clicked_at"] is not None


def test_mark_clicked_unknown_id_returns_none(tmp_path):
    store = _store(tmp_path)
    assert store.mark_clicked(99999) is None


def test_prune_old_keeps_fresh(tmp_path):
    store = _store(tmp_path)
    store.add_items([_item("u1")])  # fetched_at = now
    assert store.prune_old(days=30) == 0
    assert len(store.get_recent()) == 1


def test_prune_old_removes_stale_rows(tmp_path):
    store = _store(tmp_path)
    store.add_items([_item("old"), _item("fresh")])
    stale = (datetime.now(UTC) - timedelta(days=45)).isoformat()
    store.conn.execute("UPDATE feed_items SET fetched_at = ? WHERE url = ?", (stale, "old"))
    store.conn.commit()
    assert store.prune_old(days=30) == 1
    assert [r["url"] for r in store.get_recent()] == ["fresh"]


def test_reopening_the_same_db_keeps_items(tmp_path):
    store = _store(tmp_path)
    store.add_items([_item("u1")])
    store.close()
    assert len(FeedStore(tmp_path / "feed.db").get_recent()) == 1
