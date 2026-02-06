"""SQLite FTS5 lexical store for BM25 search."""

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from secondbrain.models import Chunk

logger = logging.getLogger(__name__)


class LexicalStore:
    """Lexical store using SQLite FTS5 for BM25 search."""

    def __init__(self, db_path: Path) -> None:
        """Initialize the lexical store.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        # Epoch-based invalidation: detect external reindex
        self._epoch_file = db_path.parent / ".reindex_epoch"
        self._last_epoch_check = 0.0
        self._known_epoch_mtime = 0.0

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._init_schema()
        return self._conn

    def _reconnect(self) -> None:
        """Close and discard the current connection so the next access creates a fresh one."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _rebuild_fts(self) -> None:
        """Rebuild the FTS5 index from the content table.

        INSERT OR REPLACE triggers can corrupt the FTS5 shadow tables.
        Rebuilding after writes ensures the index stays consistent.
        """
        self.conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        self.conn.commit()

    def _check_epoch(self) -> None:
        """Check if another process reindexed and reconnect if so."""
        now = time.time()
        if now - self._last_epoch_check < 1.0:
            return
        self._last_epoch_check = now
        try:
            mtime = self._epoch_file.stat().st_mtime
            if mtime > self._known_epoch_mtime:
                if self._known_epoch_mtime > 0:
                    logger.info("LexicalStore: external reindex detected, reconnecting")
                    self._reconnect()
                self._known_epoch_mtime = mtime
        except FileNotFoundError:
            pass

    def _init_schema(self) -> None:
        """Initialize the database schema.

        FTS5 is configured as an external-content table (content='chunks')
        WITHOUT triggers.  Triggers + INSERT OR REPLACE corrupt FTS5 shadow
        tables.  Instead, we call _rebuild_fts() after every write to the
        chunks table.  This is the approach recommended by the SQLite docs:
        "the application may arrange to call the rebuild command after all
        writes to the content table are complete."
        """
        self.conn.executescript("""
            -- Main chunks table
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                note_path TEXT NOT NULL,
                note_title TEXT NOT NULL,
                heading_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                checksum TEXT NOT NULL
            );

            -- FTS5 virtual table for full-text search (external content, NO triggers)
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id,
                note_title,
                chunk_text,
                content='chunks',
                content_rowid='rowid'
            );

            -- Drop legacy triggers that cause FTS5 corruption
            DROP TRIGGER IF EXISTS chunks_ai;
            DROP TRIGGER IF EXISTS chunks_ad;
            DROP TRIGGER IF EXISTS chunks_au;

            -- Index for faster lookups
            CREATE INDEX IF NOT EXISTS idx_chunks_note_path ON chunks(note_path);
        """)
        self.conn.commit()

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """Add or update chunks in the store.

        Args:
            chunks: List of chunks to add.
        """
        if not chunks:
            return

        rows = [
            (
                c.chunk_id,
                c.note_path,
                c.note_title,
                "|".join(c.heading_path),
                c.chunk_index,
                c.chunk_text,
                c.checksum,
            )
            for c in chunks
        ]

        sql = """
            INSERT OR REPLACE INTO chunks
            (chunk_id, note_path, note_title, heading_path, chunk_index, chunk_text, checksum)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        try:
            self.conn.executemany(sql, rows)
            self.conn.commit()
            self._rebuild_fts()
        except sqlite3.DatabaseError:
            logger.warning("LexicalStore: DatabaseError on add_chunks, reconnecting")
            self._reconnect()
            self.conn.executemany(sql, rows)
            self.conn.commit()
            self._rebuild_fts()

    def search(self, query: str, top_k: int = 50) -> list[tuple[str, float]]:
        """Search for chunks using BM25.

        Args:
            query: The search query.
            top_k: Number of results to return.

        Returns:
            List of (chunk_id, bm25_score) tuples, sorted by relevance.
        """
        self._check_epoch()

        # Escape special FTS5 characters
        escaped_query = self._escape_fts_query(query)
        sql = """
            SELECT chunk_id, bm25(chunks_fts) as score
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
            ORDER BY score
            LIMIT ?
        """

        try:
            cursor = self.conn.execute(sql, (escaped_query, top_k))
        except sqlite3.DatabaseError:
            logger.warning("LexicalStore: DatabaseError on search, reconnecting")
            self._reconnect()
            cursor = self.conn.execute(sql, (escaped_query, top_k))

        # BM25 scores are negative (lower is better), so we negate them
        return [(row["chunk_id"], -row["score"]) for row in cursor.fetchall()]

    def _escape_fts_query(self, query: str) -> str:
        """Escape special characters in FTS5 query."""
        # Remove special characters that might break FTS5
        special_chars = ['"', "'", "(", ")", "*", "-", "+", ":", "^", "~"]
        escaped = query
        for char in special_chars:
            escaped = escaped.replace(char, " ")

        # Split into words and wrap each in quotes for exact matching
        words = escaped.split()
        if not words:
            return '""'

        # Join words with OR for more flexible matching
        return " OR ".join(f'"{word}"' for word in words if word)

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Get a chunk by ID.

        Args:
            chunk_id: The chunk ID.

        Returns:
            Chunk data as a dict, or None if not found.
        """
        try:
            cursor = self.conn.execute(
                "SELECT * FROM chunks WHERE chunk_id = ?",
                (chunk_id,),
            )
        except sqlite3.DatabaseError:
            logger.warning("LexicalStore: DatabaseError on get_chunk, reconnecting")
            self._reconnect()
            cursor = self.conn.execute(
                "SELECT * FROM chunks WHERE chunk_id = ?",
                (chunk_id,),
            )
        row = cursor.fetchone()
        return dict(row) if row else None

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        """Delete chunks by ID."""
        if not chunk_ids:
            return
        placeholders = ",".join("?" for _ in chunk_ids)
        sql = f"DELETE FROM chunks WHERE chunk_id IN ({placeholders})"
        try:
            self.conn.execute(sql, chunk_ids)
            self.conn.commit()
            self._rebuild_fts()
        except sqlite3.DatabaseError:
            logger.warning("LexicalStore: DatabaseError on delete_chunks, reconnecting")
            self._reconnect()
            self.conn.execute(sql, chunk_ids)
            self.conn.commit()
            self._rebuild_fts()

    def delete_by_note_path(self, note_path: str) -> list[str]:
        """Delete all chunks for a note and return their IDs.

        Args:
            note_path: The note path.

        Returns:
            List of deleted chunk IDs.
        """
        try:
            cursor = self.conn.execute(
                "SELECT chunk_id FROM chunks WHERE note_path = ?",
                (note_path,),
            )
            chunk_ids = [row["chunk_id"] for row in cursor.fetchall()]

            if chunk_ids:
                self.conn.execute(
                    "DELETE FROM chunks WHERE note_path = ?",
                    (note_path,),
                )
                self.conn.commit()
                self._rebuild_fts()
        except sqlite3.DatabaseError:
            logger.warning("LexicalStore: DatabaseError on delete_by_note_path, reconnecting")
            self._reconnect()
            cursor = self.conn.execute(
                "SELECT chunk_id FROM chunks WHERE note_path = ?",
                (note_path,),
            )
            chunk_ids = [row["chunk_id"] for row in cursor.fetchall()]

            if chunk_ids:
                self.conn.execute(
                    "DELETE FROM chunks WHERE note_path = ?",
                    (note_path,),
                )
                self.conn.commit()
                self._rebuild_fts()

        return chunk_ids

    def count(self) -> int:
        """Get the number of chunks in the store."""
        try:
            cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        except sqlite3.DatabaseError:
            logger.warning("LexicalStore: DatabaseError on count, reconnecting")
            self._reconnect()
            cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        result = cursor.fetchone()
        return int(result[0]) if result else 0

    def clear(self) -> None:
        """Clear all chunks from the store."""
        try:
            self.conn.execute("DELETE FROM chunks")
            self.conn.commit()
            self._rebuild_fts()
        except sqlite3.DatabaseError:
            logger.warning("LexicalStore: DatabaseError on clear, reconnecting")
            self._reconnect()
            self.conn.execute("DELETE FROM chunks")
            self.conn.commit()
            self._rebuild_fts()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
