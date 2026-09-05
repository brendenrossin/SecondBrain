import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

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


class TestReconnectRetry:
    """The store's only resilience mechanism — previously untested."""

    def test_run_retries_once_after_a_database_error(self, tmp_path):
        store = _store(tmp_path)
        store.add_items([_item("u1")])
        real_conn = store.conn
        calls = {"n": 0}

        class FlakyConn:
            """Fails the first execute, then the retry hits a fresh real connection."""

            def __getattr__(self, name):
                return getattr(real_conn, name)

            def execute(self, _sql, _params=()):
                calls["n"] += 1
                raise sqlite3.DatabaseError("disk I/O error")

        store._conn = FlakyConn()  # type: ignore[assignment]
        rows = store.get_recent()
        assert calls["n"] == 1
        assert [r["url"] for r in rows] == ["u1"]

    def test_run_many_retries_once_after_a_database_error(self, tmp_path):
        store = _store(tmp_path)
        store.add_items([_item("u1")])
        real_conn = store.conn
        calls = {"n": 0}

        class FlakyConn:
            def __getattr__(self, name):
                return getattr(real_conn, name)

            def executemany(self, _sql, _rows):
                calls["n"] += 1
                raise sqlite3.DatabaseError("disk I/O error")

        store._conn = FlakyConn()  # type: ignore[assignment]
        store.update_summaries([_item("u1", summary="take")])
        assert calls["n"] == 1
        assert FeedStore(tmp_path / "feed.db").get_recent()[0]["summary"] == "take"

    def test_a_persistent_error_propagates_rather_than_looping(self, tmp_path):
        """One retry, not an infinite one — a genuinely corrupt db must surface."""
        store = _store(tmp_path)
        store.add_items([_item("u1")])

        class DeadConn:
            def execute(self, *_a, **_k):
                raise sqlite3.DatabaseError("file is not a database")

            def close(self):
                pass

        store._conn = DeadConn()  # type: ignore[assignment]
        store._reconnect = lambda: None  # type: ignore[method-assign]
        with pytest.raises(sqlite3.DatabaseError):
            store.get_recent()


class TestScoreRefresh:
    def test_rerunning_refreshes_score_and_freshness(self, tmp_path):
        """INSERT OR IGNORE would freeze a day-one score for the whole 30d window."""
        store = _store(tmp_path)
        store.add_items([_item("u1", score=9.0)])
        first = store.get_recent()[0]
        store.add_items([_item("u1", score=1.0)])
        second = store.get_recent()[0]
        assert second["score"] == 1.0
        assert second["fetched_at"] >= first["fetched_at"]

    def test_upsert_preserves_engagement_and_summary(self, tmp_path):
        store = _store(tmp_path)
        store.add_items([_item("u1")])
        store.update_summaries([_item("u1", summary="take")])
        store.mark_shown(["u1"])
        store.mark_clicked(store.get_recent()[0]["id"])

        store.add_items([_item("u1", score=2.0)])  # a later refresh
        row = store.get_recent()[0]
        assert row["summary"] == "take"
        assert row["shown_at"] is not None
        assert row["clicked_at"] is not None
        assert row["score"] == 2.0

    def test_reinsert_is_not_counted_as_new(self, tmp_path):
        store = _store(tmp_path)
        assert store.add_items([_item("u1"), _item("u2")]) == 2
        assert store.add_items([_item("u1"), _item("u3")]) == 1


class TestSummarizedSince:
    def test_only_returns_summarized_rows_in_window(self, tmp_path):
        store = _store(tmp_path)
        items = [_item("fresh", summary="t"), _item("stale", summary="t"), _item("raw")]
        store.add_items(items)
        store.update_summaries(items)
        old = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        store.conn.execute("UPDATE feed_items SET fetched_at = ? WHERE url = ?", (old, "stale"))
        store.conn.commit()
        cutoff = (datetime.now(UTC) - timedelta(hours=20)).isoformat()
        assert [r["url"] for r in store.get_summarized_since(cutoff)] == ["fresh"]

    def test_last_fetched_at_is_none_when_empty(self, tmp_path):
        assert _store(tmp_path).last_fetched_at() is None

    def test_last_fetched_at_returns_newest(self, tmp_path):
        store = _store(tmp_path)
        store.add_items([_item("u1")])
        assert store.last_fetched_at() == store.get_recent()[0]["fetched_at"]
