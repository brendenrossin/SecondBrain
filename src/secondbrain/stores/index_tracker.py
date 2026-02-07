"""SQLite-backed tracker for incremental indexing."""

import contextlib
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class IndexTracker:
    """Tracks which files have been indexed and their content hashes.

    Uses same patterns as LexicalStore: WAL mode, busy_timeout, reconnect-on-error.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._init_schema()
        return self._conn

    def _reconnect(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS indexed_files (
                file_path TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                last_modified REAL NOT NULL,
                last_indexed_at TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0
            );
        """)
        self.conn.commit()

    def classify_changes(
        self,
        vault_files: dict[str, tuple[float, str]],
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        """Classify vault files into new, modified, deleted, unchanged.

        Args:
            vault_files: {file_path: (mtime, content_hash)} from vault scan.

        Returns:
            Tuple of (new_files, modified_files, deleted_files, unchanged_files).
        """
        try:
            cursor = self.conn.execute(
                "SELECT file_path, content_hash, last_modified FROM indexed_files"
            )
        except sqlite3.DatabaseError:
            logger.warning("IndexTracker: DatabaseError on classify, reconnecting")
            self._reconnect()
            cursor = self.conn.execute(
                "SELECT file_path, content_hash, last_modified FROM indexed_files"
            )

        indexed: dict[str, tuple[str, float]] = {}
        for row in cursor.fetchall():
            indexed[row["file_path"]] = (row["content_hash"], row["last_modified"])

        new_files: list[str] = []
        modified_files: list[str] = []
        unchanged_files: list[str] = []

        for file_path, (mtime, content_hash) in vault_files.items():
            if file_path not in indexed:
                new_files.append(file_path)
            else:
                stored_hash, stored_mtime = indexed[file_path]
                # Fast path: mtime unchanged -> skip hash comparison
                if mtime == stored_mtime:
                    unchanged_files.append(file_path)
                elif content_hash != stored_hash:
                    modified_files.append(file_path)
                else:
                    # mtime changed but content same -> unchanged
                    unchanged_files.append(file_path)

        # Files in index but not in vault -> deleted
        vault_set = set(vault_files.keys())
        deleted_files = [fp for fp in indexed if fp not in vault_set]

        return new_files, modified_files, deleted_files, unchanged_files

    def mark_indexed(
        self,
        file_path: str,
        content_hash: str,
        mtime: float,
        chunk_count: int,
    ) -> None:
        """Record that a file has been indexed."""
        now = datetime.now(UTC).isoformat()
        sql = """
            INSERT OR REPLACE INTO indexed_files
            (file_path, content_hash, last_modified, last_indexed_at, chunk_count)
            VALUES (?, ?, ?, ?, ?)
        """
        try:
            self.conn.execute(sql, (file_path, content_hash, mtime, now, chunk_count))
            self.conn.commit()
        except sqlite3.DatabaseError:
            logger.warning("IndexTracker: DatabaseError on mark_indexed, reconnecting")
            self._reconnect()
            self.conn.execute(sql, (file_path, content_hash, mtime, now, chunk_count))
            self.conn.commit()

    def remove_file(self, file_path: str) -> None:
        """Remove a file from the tracker."""
        try:
            self.conn.execute("DELETE FROM indexed_files WHERE file_path = ?", (file_path,))
            self.conn.commit()
        except sqlite3.DatabaseError:
            logger.warning("IndexTracker: DatabaseError on remove_file, reconnecting")
            self._reconnect()
            self.conn.execute("DELETE FROM indexed_files WHERE file_path = ?", (file_path,))
            self.conn.commit()

    def clear(self) -> None:
        """Clear all tracking data."""
        try:
            self.conn.execute("DELETE FROM indexed_files")
            self.conn.commit()
        except sqlite3.DatabaseError:
            logger.warning("IndexTracker: DatabaseError on clear, reconnecting")
            self._reconnect()
            self.conn.execute("DELETE FROM indexed_files")
            self.conn.commit()

    def get_stats(self) -> dict[str, int | str | None]:
        """Return summary stats: file_count, total_chunks, last_indexed_at."""
        sql = """
            SELECT
                COUNT(*) AS file_count,
                COALESCE(SUM(chunk_count), 0) AS total_chunks,
                MAX(last_indexed_at) AS last_indexed_at
            FROM indexed_files
        """
        try:
            row = self.conn.execute(sql).fetchone()
        except sqlite3.DatabaseError:
            logger.warning("IndexTracker: DatabaseError on get_stats, reconnecting")
            self._reconnect()
            row = self.conn.execute(sql).fetchone()
        return {
            "file_count": row["file_count"],
            "total_chunks": row["total_chunks"],
            "last_indexed_at": row["last_indexed_at"],
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
