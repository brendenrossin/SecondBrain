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
        """Insert items, ignoring URLs already stored. Returns the count newly inserted."""
        if not items:
            return 0
        now = datetime.now(UTC).isoformat()
        cursor = self._run_many(
            """INSERT OR IGNORE INTO feed_items
               (url, source_label, type, title, snippet, published_at, fetched_at, score, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
        return cursor.rowcount

    def update_summaries(self, items: list[FeedItem]) -> None:
        """Write back the per-item take and final score for items that were summarized."""
        rows = [(it.summary, it.score, it.url) for it in items if it.summary is not None]
        if not rows:
            return
        self._run_many("UPDATE feed_items SET summary = ?, score = ? WHERE url = ?", rows)
        self.conn.commit()

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Highest-scoring items first, newest as the tiebreak."""
        rows = self._run(
            "SELECT * FROM feed_items ORDER BY score DESC, fetched_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

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
        if self._conn is not None:
            self._conn.close()
            self._conn = None
