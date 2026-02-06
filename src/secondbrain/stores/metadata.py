"""SQLite store for extracted note metadata."""

import contextlib
import json
import logging
import sqlite3
from pathlib import Path

from secondbrain.models import ActionItem, DateMention, Entity, NoteMetadata

logger = logging.getLogger(__name__)


class MetadataStore:
    """Store for LLM-extracted note metadata."""

    def __init__(self, db_path: Path) -> None:
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
            self._init_schema()
        return self._conn

    def _reconnect(self) -> None:
        """Close and discard the current connection."""
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS note_metadata (
                note_path TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                key_phrases TEXT NOT NULL,
                entities TEXT NOT NULL,
                dates TEXT NOT NULL,
                action_items TEXT NOT NULL,
                extracted_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                model_used TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_metadata_extracted_at
                ON note_metadata(extracted_at);
        """)
        self.conn.commit()

    def _execute(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Cursor:
        """Execute SQL with auto-reconnect on error."""
        try:
            return self.conn.execute(sql, params)
        except sqlite3.DatabaseError:
            logger.warning("MetadataStore: DatabaseError, reconnecting")
            self._reconnect()
            return self.conn.execute(sql, params)

    def upsert(self, metadata: NoteMetadata) -> None:
        """Insert or update metadata for a note."""
        sql = """
            INSERT OR REPLACE INTO note_metadata
            (note_path, summary, key_phrases, entities, dates, action_items,
             extracted_at, content_hash, model_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            metadata.note_path,
            metadata.summary,
            json.dumps(list(metadata.key_phrases)),
            json.dumps([e.model_dump() for e in metadata.entities]),
            json.dumps([d.model_dump() for d in metadata.dates]),
            json.dumps([a.model_dump() for a in metadata.action_items]),
            metadata.extracted_at,
            metadata.content_hash,
            metadata.model_used,
        )
        self._execute(sql, params)
        self.conn.commit()

    def get(self, note_path: str) -> NoteMetadata | None:
        """Get metadata for a single note."""
        cursor = self._execute(
            "SELECT * FROM note_metadata WHERE note_path = ?", (note_path,)
        )
        row = cursor.fetchone()
        return self._row_to_metadata(row) if row else None

    def get_all(self) -> list[NoteMetadata]:
        """Get metadata for all notes."""
        cursor = self._execute(
            "SELECT * FROM note_metadata ORDER BY note_path"
        )
        return [self._row_to_metadata(row) for row in cursor.fetchall()]

    def delete(self, note_path: str) -> None:
        """Delete metadata for a note."""
        self._execute("DELETE FROM note_metadata WHERE note_path = ?", (note_path,))
        self.conn.commit()

    def get_stale(self, current_hashes: dict[str, str]) -> list[str]:
        """Find notes whose metadata is stale (hash mismatch or missing)."""
        cursor = self._execute("SELECT note_path, content_hash FROM note_metadata")
        stored = {row["note_path"]: row["content_hash"] for row in cursor.fetchall()}

        return [
            path for path, h in current_hashes.items()
            if stored.get(path) != h
        ]

    def count(self) -> int:
        """Get the number of notes with metadata."""
        cursor = self._execute("SELECT COUNT(*) FROM note_metadata")
        result = cursor.fetchone()
        return int(result[0]) if result else 0

    def clear(self) -> None:
        """Clear all metadata."""
        self._execute("DELETE FROM note_metadata")
        self.conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _row_to_metadata(row: sqlite3.Row) -> NoteMetadata:
        """Convert a database row to a NoteMetadata model."""
        return NoteMetadata(
            note_path=row["note_path"],
            summary=row["summary"],
            key_phrases=json.loads(row["key_phrases"]),
            entities=[Entity(**e) for e in json.loads(row["entities"])],
            dates=[DateMention(**d) for d in json.loads(row["dates"])],
            action_items=[ActionItem(**a) for a in json.loads(row["action_items"])],
            extracted_at=row["extracted_at"],
            content_hash=row["content_hash"],
            model_used=row["model_used"],
        )
