"""Transient feed item store (SQLite, WAL).

Feed items are derived data, never vault content — they are re-fetchable, pruned at
30 days, and the vault stays the source of truth for anything the user chooses to keep.
"""

import contextlib
import logging
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from secondbrain.feed.models import FeedItem

logger = logging.getLogger(__name__)


class FeedStore:
    """SQLite-based store for fetched feed items, deduped on URL."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create the database connection."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA wal_autocheckpoint=1000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._init_schema()
        return self._conn

    def _reconnect(self) -> None:
        """Close and discard the current connection so the next access creates a fresh one."""
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None

    def _run(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute one statement, reconnecting and retrying once on a database error."""
        try:
            return self.conn.execute(sql, params)
        except sqlite3.DatabaseError:
            logger.warning("FeedStore: DatabaseError, reconnecting")
            self._reconnect()
            return self.conn.execute(sql, params)

    def _run_many(self, sql: str, params_seq: Iterable[tuple[Any, ...]]) -> sqlite3.Cursor:
        """Execute one statement over many parameter tuples, retrying once on error."""
        rows = list(params_seq)
        try:
            return self.conn.executemany(sql, rows)
        except sqlite3.DatabaseError:
            logger.warning("FeedStore: DatabaseError on batch, reconnecting")
            self._reconnect()
            return self.conn.executemany(sql, rows)

    def _count(self) -> int:
        row = self._run("SELECT COUNT(*) AS n FROM feed_items").fetchone()
        return int(row["n"])

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS feed_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                source_label TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                snippet TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                summary TEXT,
                shown_at TEXT,
                clicked_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_feed_score ON feed_items(score DESC);
            CREATE INDEX IF NOT EXISTS idx_feed_fetched ON feed_items(fetched_at);
        """)
        self.conn.commit()

    def add_items(self, items: list[FeedItem]) -> int:
        """Upsert items keyed on URL. Returns the count of rows newly inserted.

        A URL already stored has its score, freshness and text refreshed rather
        than ignored: the ranking formula has a 48-hour recency half-life, so a
        score frozen at first insert would let day-one items outrank fresh ones
        for the whole 30-day retention window. Engagement columns (shown_at,
        clicked_at) and the LLM summary are deliberately preserved.
        """
        if not items:
            return 0
        now = datetime.now(UTC).isoformat()
        before = self._count()
        self._run_many(
            """INSERT INTO feed_items
               (url, source_label, type, title, snippet, published_at, fetched_at, score, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET
                   score = excluded.score,
                   fetched_at = excluded.fetched_at,
                   title = excluded.title,
                   snippet = excluded.snippet,
                   published_at = excluded.published_at""",
            [
                (
                    it.url,
                    it.source_label,
                    it.type,
                    it.title,
                    it.snippet,
                    it.published_at,
                    now,
                    it.score,
                    it.summary,
                )
                for it in items
            ],
        )
        self.conn.commit()
        return self._count() - before

    def update_summaries(self, items: list[FeedItem]) -> None:
        """Write back the per-item take and final score for items that were summarized."""
        rows = [(it.summary, it.score, it.url) for it in items if it.summary is not None]
        if not rows:
            return
        self._run_many("UPDATE feed_items SET summary = ?, score = ? WHERE url = ?", rows)
        self.conn.commit()

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Newest refresh first, best-scoring within it.

        Ordering by score alone would let a high-scoring item from an earlier run
        outrank everything fetched since, turning the feed into a museum.
        """
        rows = self._run(
            "SELECT * FROM feed_items ORDER BY fetched_at DESC, score DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def get_summarized_since(self, since_iso: str, limit: int = 50) -> list[dict[str, Any]]:
        """Summarized items from refreshes at or after `since_iso`.

        Used for the daily digest count, which must reflect *this* refresh — not
        an all-time top-N that would report the same numbers every morning.
        """
        rows = self._run(
            """SELECT * FROM feed_items
               WHERE summary IS NOT NULL AND fetched_at >= ?
               ORDER BY fetched_at DESC, score DESC LIMIT ?""",
            (since_iso, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def last_fetched_at(self) -> str | None:
        """ISO timestamp of the most recent refresh, or None if the store is empty."""
        row = self._run("SELECT MAX(fetched_at) AS ts FROM feed_items").fetchone()
        return str(row["ts"]) if row and row["ts"] else None

    def mark_shown(self, urls: list[str]) -> None:
        """Stamp first-seen time; a re-show keeps the original timestamp."""
        if not urls:
            return
        now = datetime.now(UTC).isoformat()
        self._run_many(
            "UPDATE feed_items SET shown_at = COALESCE(shown_at, ?) WHERE url = ?",
            [(now, url) for url in urls],
        )
        self.conn.commit()

    def mark_clicked(self, item_id: int) -> str | None:
        """Record a click. Returns the item's URL, or None if the id is unknown."""
        row = self._run("SELECT url FROM feed_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return None
        self._run(
            "UPDATE feed_items SET clicked_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), item_id),
        )
        self.conn.commit()
        return str(row["url"])

    def prune_old(self, days: int = 30) -> int:
        """Delete items fetched more than `days` ago. Returns the number removed."""
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        cursor = self._run("DELETE FROM feed_items WHERE fetched_at < ?", (cutoff,))
        self.conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        """Always called from a finally — must never mask the original exception."""
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None
