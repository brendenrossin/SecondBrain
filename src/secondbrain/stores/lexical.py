"""SQLite FTS5 lexical store for BM25 search."""

import sqlite3
from pathlib import Path
from typing import Any

from secondbrain.models import Chunk


class LexicalStore:
    """Lexical store using SQLite FTS5 for BM25 search."""

    def __init__(self, db_path: Path) -> None:
        """Initialize the lexical store.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        """Initialize the database schema."""
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

            -- FTS5 virtual table for full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id,
                note_title,
                chunk_text,
                content='chunks',
                content_rowid='rowid'
            );

            -- Triggers to keep FTS in sync
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, chunk_id, note_title, chunk_text)
                VALUES (new.rowid, new.chunk_id, new.note_title, new.chunk_text);
            END;

            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, note_title, chunk_text)
                VALUES('delete', old.rowid, old.chunk_id, old.note_title, old.chunk_text);
            END;

            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, note_title, chunk_text)
                VALUES('delete', old.rowid, old.chunk_id, old.note_title, old.chunk_text);
                INSERT INTO chunks_fts(rowid, chunk_id, note_title, chunk_text)
                VALUES (new.rowid, new.chunk_id, new.note_title, new.chunk_text);
            END;

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

        self.conn.executemany(
            """
            INSERT OR REPLACE INTO chunks
            (chunk_id, note_path, note_title, heading_path, chunk_index, chunk_text, checksum)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
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
            ],
        )
        self.conn.commit()

    def search(self, query: str, top_k: int = 50) -> list[tuple[str, float]]:
        """Search for chunks using BM25.

        Args:
            query: The search query.
            top_k: Number of results to return.

        Returns:
            List of (chunk_id, bm25_score) tuples, sorted by relevance.
        """
        # Escape special FTS5 characters
        escaped_query = self._escape_fts_query(query)

        cursor = self.conn.execute(
            """
            SELECT chunk_id, bm25(chunks_fts) as score
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (escaped_query, top_k),
        )

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
        cursor = self.conn.execute(
            "SELECT * FROM chunks WHERE chunk_id = ?",
            (chunk_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        """Delete chunks by ID."""
        if chunk_ids:
            placeholders = ",".join("?" for _ in chunk_ids)
            self.conn.execute(
                f"DELETE FROM chunks WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            )
            self.conn.commit()

    def delete_by_note_path(self, note_path: str) -> list[str]:
        """Delete all chunks for a note and return their IDs.

        Args:
            note_path: The note path.

        Returns:
            List of deleted chunk IDs.
        """
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

        return chunk_ids

    def count(self) -> int:
        """Get the number of chunks in the store."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        result = cursor.fetchone()
        return int(result[0]) if result else 0

    def clear(self) -> None:
        """Clear all chunks from the store."""
        self.conn.execute("DELETE FROM chunks")
        self.conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
