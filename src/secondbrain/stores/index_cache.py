"""SQLite-backed cache for context blurbs and embeddings during indexing."""

import contextlib
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class IndexCache:
    """Cache for context blurbs and embeddings to avoid recomputation during re-indexing.

    Two tables:
    - blurb_cache: keyed by (text_hash, model), stores the generated context blurb string.
    - embedding_cache: keyed by (text_hash, model), stores serialized float32 embedding vectors.

    Callers are responsible for computing the text_hash (SHA1 hex digest of the chunk text).
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize the index cache.

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

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS blurb_cache (
                text_hash TEXT NOT NULL,
                model TEXT NOT NULL,
                blurb TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (text_hash, model)
            );

            CREATE TABLE IF NOT EXISTS embedding_cache (
                text_hash TEXT NOT NULL,
                model TEXT NOT NULL,
                embedding BLOB NOT NULL,
                dimensions INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (text_hash, model)
            );
        """)
        self._conn.commit()

    def get_blurb(self, text_hash: str, model: str) -> str | None:
        """Return the cached blurb for (text_hash, model), or None on a miss.

        Args:
            text_hash: SHA1 hex digest of the chunk text.
            model: Model identifier used to generate the blurb.

        Returns:
            Cached blurb string, or None if not found.
        """
        sql = "SELECT blurb FROM blurb_cache WHERE text_hash = ? AND model = ?"
        try:
            cursor = self.conn.execute(sql, (text_hash, model))
        except sqlite3.DatabaseError:
            logger.warning("IndexCache: DatabaseError on get_blurb, reconnecting")
            self._reconnect()
            cursor = self.conn.execute(sql, (text_hash, model))
        row = cursor.fetchone()
        return row["blurb"] if row else None

    def set_blurb(self, text_hash: str, model: str, blurb: str) -> None:
        """Store a blurb in the cache.

        Args:
            text_hash: SHA1 hex digest of the chunk text.
            model: Model identifier used to generate the blurb.
            blurb: The context blurb string to cache.
        """
        sql = """
            INSERT OR REPLACE INTO blurb_cache (text_hash, model, blurb, created_at)
            VALUES (?, ?, ?, ?)
        """
        now = datetime.now(UTC).isoformat()
        try:
            self.conn.execute(sql, (text_hash, model, blurb, now))
            self.conn.commit()
        except sqlite3.DatabaseError:
            logger.warning("IndexCache: DatabaseError on set_blurb, reconnecting")
            self._reconnect()
            self.conn.execute(sql, (text_hash, model, blurb, now))
            self.conn.commit()

    def get_embedding(self, text_hash: str, model: str) -> NDArray[np.float32] | None:
        """Return the cached embedding for (text_hash, model), or None on a miss.

        Args:
            text_hash: SHA1 hex digest of the chunk text.
            model: Model identifier used to generate the embedding.

        Returns:
            float32 numpy array, or None if not found.
        """
        sql = "SELECT embedding, dimensions FROM embedding_cache WHERE text_hash = ? AND model = ?"
        try:
            cursor = self.conn.execute(sql, (text_hash, model))
        except sqlite3.DatabaseError:
            logger.warning("IndexCache: DatabaseError on get_embedding, reconnecting")
            self._reconnect()
            cursor = self.conn.execute(sql, (text_hash, model))
        row = cursor.fetchone()
        if row is None:
            return None
        return np.frombuffer(row["embedding"], dtype=np.float32).reshape(row["dimensions"])

    def set_embedding(self, text_hash: str, model: str, embedding: NDArray[np.float32]) -> None:
        """Store an embedding in the cache.

        Args:
            text_hash: SHA1 hex digest of the chunk text.
            model: Model identifier used to generate the embedding.
            embedding: float32 numpy array to cache.
        """
        sql = """
            INSERT OR REPLACE INTO embedding_cache
                (text_hash, model, embedding, dimensions, created_at)
            VALUES (?, ?, ?, ?, ?)
        """
        now = datetime.now(UTC).isoformat()
        blob = embedding.tobytes()
        dimensions = embedding.shape[0]
        try:
            self.conn.execute(sql, (text_hash, model, blob, dimensions, now))
            self.conn.commit()
        except sqlite3.DatabaseError:
            logger.warning("IndexCache: DatabaseError on set_embedding, reconnecting")
            self._reconnect()
            self.conn.execute(sql, (text_hash, model, blob, dimensions, now))
            self.conn.commit()

    def clear(self) -> None:
        """Remove all entries from both caches."""
        try:
            self.conn.execute("DELETE FROM blurb_cache")
            self.conn.execute("DELETE FROM embedding_cache")
            self.conn.commit()
        except sqlite3.DatabaseError:
            logger.warning("IndexCache: DatabaseError on clear, reconnecting")
            self._reconnect()
            self.conn.execute("DELETE FROM blurb_cache")
            self.conn.execute("DELETE FROM embedding_cache")
            self.conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
