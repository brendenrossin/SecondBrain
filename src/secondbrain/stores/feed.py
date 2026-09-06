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
from secondbrain.feed.text import strip_html

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1


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

            CREATE TABLE IF NOT EXISTS feed_section_overviews (
                type TEXT PRIMARY KEY,
                overview TEXT NOT NULL,
                generated_at TEXT NOT NULL
            );
        """)
        self.conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """Run one-time data fixes, tracked in PRAGMA user_version.

        v1 strips HTML from rows stored before `fetch` cleaned text at ingestion.
        A refresh only rewrites items still present in their source feed, so an
        article that has since aged out of its RSS window would otherwise keep
        raw markup on screen until the 30-day prune reached it.

        Uses `self.conn` directly rather than the `_run` helpers on purpose: this
        runs inside `_init_schema`, and `_run`'s reconnect would re-enter the
        `conn` property and recurse until the stack blew.
        """
        try:
            version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
            if version >= _SCHEMA_VERSION:
                return
            self._backfill_plain_text()
            # PRAGMA user_version is transactional, so it commits with the rows
            # it describes — never a bumped version over unwritten data.
            self.conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            self.conn.commit()
        except sqlite3.Error:
            # Roll back, or the half-finished pass stays pending on this
            # connection: it holds a write lock the other process blocks on, and
            # the next unrelated commit() would persist it under version 0 —
            # leaving the retry to strip already-stripped rows a second time.
            with contextlib.suppress(Exception):
                self.conn.rollback()
            logger.warning("FeedStore: plain-text backfill failed", exc_info=True)

    def _backfill_plain_text(self) -> None:
        """Rewrite any title/snippet still holding markup or HTML entities."""
        rows = self.conn.execute(
            """SELECT id, title, snippet FROM feed_items
               WHERE title LIKE '%<%' OR title LIKE '%&%'
                  OR snippet LIKE '%<%' OR snippet LIKE '%&%'"""
        ).fetchall()
        updates: list[tuple[str, str | None, int]] = []
        for row in rows:
            stored_snippet = row["snippet"] or ""
            title = strip_html(row["title"])
            snippet = strip_html(stored_snippet)
            if title == row["title"] and snippet == stored_snippet:
                continue
            # Keep the original when stripping empties a field — markup-only
            # text is still better than a blank row, and these rewrites are
            # in place with no copy of the original to recover from.
            updates.append((title or row["title"], snippet or row["snippet"], row["id"]))
        if updates:
            self.conn.executemany(
                "UPDATE feed_items SET title = ?, snippet = ? WHERE id = ?", updates
            )
            logger.info("FeedStore: stripped markup from %d rows", len(updates))

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

    def replace_section_overviews(self, overviews: dict[str, str]) -> None:
        """Swap in this run's section overviews, keyed by item type.

        A full replace, not an upsert: an overview describes one refresh's
        stories, so a type that produced nothing today must not keep yesterday's
        paragraph sitting above today's headlines.
        """
        now = datetime.now(UTC).isoformat()
        self._run("DELETE FROM feed_section_overviews")
        if overviews:
            # OR REPLACE, not plain INSERT: `_run_many` reconnects and retries
            # once on a database error, and reconnecting rolls the DELETE back —
            # so the retry meets the rows it thought it had just removed.
            self._run_many(
                """INSERT OR REPLACE INTO feed_section_overviews
                   (type, overview, generated_at) VALUES (?, ?, ?)""",
                [(t, text, now) for t, text in overviews.items()],
            )
        self.conn.commit()

    def get_section_overviews(self) -> dict[str, str]:
        """Stored overviews by item type, e.g. {"ai": "...", "sports": "..."}."""
        rows = self._run("SELECT type, overview FROM feed_section_overviews").fetchall()
        return {str(row["type"]): str(row["overview"]) for row in rows}

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
