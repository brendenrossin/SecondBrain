"""Tests for store concurrency resilience (WAL mode, reconnect, epoch invalidation)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from secondbrain.models import Chunk
from secondbrain.stores.conversation import ConversationStore
from secondbrain.stores.lexical import LexicalStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(chunk_id: str = "c1", text: str = "hello world") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        note_path="notes/test.md",
        note_title="Test Note",
        heading_path=["H1"],
        chunk_index=0,
        chunk_text=text,
        checksum="abc123",
    )


# ---------------------------------------------------------------------------
# LexicalStore tests
# ---------------------------------------------------------------------------


class TestLexicalStoreWAL:
    """Verify LexicalStore enables WAL mode and busy timeout."""

    def test_wal_mode_enabled(self, tmp_path: Path) -> None:
        store = LexicalStore(tmp_path / "test.db")
        cursor = store.conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0] == "wal"

    def test_busy_timeout_set(self, tmp_path: Path) -> None:
        store = LexicalStore(tmp_path / "test.db")
        cursor = store.conn.execute("PRAGMA busy_timeout")
        assert cursor.fetchone()[0] == 5000

    def test_basic_add_and_search(self, tmp_path: Path) -> None:
        store = LexicalStore(tmp_path / "test.db")
        store.add_chunks([_make_chunk()])
        results = store.search("hello")
        assert len(results) == 1
        assert results[0][0] == "c1"

    def test_basic_count(self, tmp_path: Path) -> None:
        store = LexicalStore(tmp_path / "test.db")
        assert store.count() == 0
        store.add_chunks([_make_chunk()])
        assert store.count() == 1


class TestLexicalStoreReconnect:
    """Verify reconnect-on-error for LexicalStore."""

    def test_reconnect_resets_connection(self, tmp_path: Path) -> None:
        store = LexicalStore(tmp_path / "test.db")
        _ = store.conn  # force connection
        assert store._conn is not None
        store._reconnect()
        assert store._conn is None

    def test_search_reconnects_on_database_error(self, tmp_path: Path) -> None:
        store = LexicalStore(tmp_path / "test.db")
        store.add_chunks([_make_chunk()])

        # Corrupt the connection by closing it behind the store's back
        store._conn.close()

        # Search should reconnect and succeed
        results = store.search("hello")
        assert len(results) == 1

    def test_add_chunks_reconnects_on_database_error(self, tmp_path: Path) -> None:
        store = LexicalStore(tmp_path / "test.db")
        _ = store.conn  # init schema

        # Corrupt connection
        store._conn.close()

        # Should reconnect and succeed
        store.add_chunks([_make_chunk()])
        assert store.count() == 1

    def test_count_reconnects_on_database_error(self, tmp_path: Path) -> None:
        store = LexicalStore(tmp_path / "test.db")
        store.add_chunks([_make_chunk()])

        store._conn.close()

        assert store.count() == 1

    def test_clear_reconnects_on_database_error(self, tmp_path: Path) -> None:
        store = LexicalStore(tmp_path / "test.db")
        store.add_chunks([_make_chunk()])

        store._conn.close()

        store.clear()
        # Reconnect happened, verify store is empty
        assert store.count() == 0


class TestLexicalStoreEpoch:
    """Verify epoch-based invalidation for LexicalStore."""

    def test_epoch_triggers_reconnect(self, tmp_path: Path) -> None:
        store = LexicalStore(tmp_path / "test.db")
        store.add_chunks([_make_chunk()])

        # Simulate external reindex by writing epoch file
        epoch_file = tmp_path / ".reindex_epoch"
        epoch_file.write_text("1")

        # First check sets the baseline
        store._check_epoch()
        old_conn = store._conn

        # "New" epoch (touch the file with a newer mtime)
        import time

        time.sleep(0.05)
        epoch_file.write_text("2")

        # Force epoch check (reset timer)
        store._last_epoch_check = 0
        store._check_epoch()

        # Connection should have been reset
        assert store._conn is None or store._conn is not old_conn


class TestLexicalStoreConcurrentAccess:
    """Simulate two-process concurrent access via WAL mode."""

    def test_two_connections_wal(self, tmp_path: Path) -> None:
        """Two connections can read/write concurrently with WAL."""
        db_path = tmp_path / "test.db"

        store1 = LexicalStore(db_path)
        store1.add_chunks([_make_chunk("c1", "first chunk")])

        # Second "process" connection
        store2 = LexicalStore(db_path)

        # Store2 can read what store1 wrote
        assert store2.count() == 1

        # Store2 writes
        store2.add_chunks([_make_chunk("c2", "second chunk")])

        # Store1 can read store2's write
        assert store1.count() == 2

        # Both can search
        results1 = store1.search("second")
        results2 = store2.search("first")
        assert len(results1) >= 1
        assert len(results2) >= 1

        store1.close()
        store2.close()


class TestLexicalStoreFTSIntegrity:
    """Verify FTS5 stays consistent across repeated reindexes.

    This is the regression test for the FTS5 content-sync corruption bug:
    INSERT OR REPLACE + triggers corrupted FTS5 shadow tables.  The fix
    removes triggers and uses explicit _rebuild_fts() after writes.
    """

    def test_repeated_reindex_does_not_corrupt_fts(self, tmp_path: Path) -> None:
        """Simulate multiple full reindexes (the exact scenario that corrupted FTS5)."""
        store = LexicalStore(tmp_path / "test.db")

        chunks = [
            _make_chunk("c1", "Python programming language"),
            _make_chunk("c2", "JavaScript web development"),
            _make_chunk("c3", "Rust memory safety"),
        ]

        # Reindex 5 times (INSERT OR REPLACE same chunk_ids)
        for i in range(5):
            store.add_chunks(chunks)

            # Verify FTS integrity after each reindex
            results = store.search("Python")
            assert len(results) >= 1, f"FTS search failed on reindex {i + 1}"
            assert results[0][0] == "c1"

            results = store.search("JavaScript")
            assert len(results) >= 1, f"FTS search failed on reindex {i + 1}"

            assert store.count() == 3, f"Count wrong on reindex {i + 1}"

        # Run SQLite integrity check on FTS5
        cursor = store.conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('integrity-check')")
        # integrity-check returns 'ok' if clean, or error rows
        rows = cursor.fetchall()
        assert rows == [] or (len(rows) == 1 and rows[0][0] == "ok"), (
            f"FTS5 integrity check failed: {rows}"
        )

        store.close()

    def test_add_delete_add_cycle(self, tmp_path: Path) -> None:
        """Add chunks, delete some, add again — FTS stays consistent."""
        store = LexicalStore(tmp_path / "test.db")

        # Add initial chunks
        store.add_chunks(
            [
                _make_chunk("c1", "alpha bravo charlie"),
                _make_chunk("c2", "delta echo foxtrot"),
            ]
        )
        assert store.count() == 2
        assert len(store.search("alpha")) >= 1

        # Delete one
        store.delete_chunks(["c1"])
        assert store.count() == 1
        assert len(store.search("alpha")) == 0
        assert len(store.search("delta")) >= 1

        # Add new chunks (including a replacement for c2)
        store.add_chunks(
            [
                _make_chunk("c2", "delta echo updated"),
                _make_chunk("c3", "golf hotel india"),
            ]
        )
        assert store.count() == 2
        assert len(store.search("golf")) >= 1
        assert len(store.search("updated")) >= 1

        store.close()

    def test_no_triggers_exist(self, tmp_path: Path) -> None:
        """Verify that legacy triggers are dropped from the schema."""
        store = LexicalStore(tmp_path / "test.db")
        # Force schema init
        _ = store.conn

        cursor = store.conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        triggers = [row[0] for row in cursor.fetchall()]
        assert triggers == [], f"Unexpected triggers found: {triggers}"

        store.close()


# ---------------------------------------------------------------------------
# ConversationStore tests
# ---------------------------------------------------------------------------


class TestConversationStoreWAL:
    """Verify ConversationStore enables WAL mode and busy timeout."""

    def test_wal_mode_enabled(self, tmp_path: Path) -> None:
        store = ConversationStore(tmp_path / "conv.db")
        cursor = store.conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0] == "wal"

    def test_busy_timeout_set(self, tmp_path: Path) -> None:
        store = ConversationStore(tmp_path / "conv.db")
        cursor = store.conn.execute("PRAGMA busy_timeout")
        assert cursor.fetchone()[0] == 5000


class TestConversationStoreReconnect:
    """Verify reconnect-on-error for ConversationStore."""

    def test_reconnect_resets_connection(self, tmp_path: Path) -> None:
        store = ConversationStore(tmp_path / "conv.db")
        _ = store.conn
        assert store._conn is not None
        store._reconnect()
        assert store._conn is None

    def test_create_conversation_reconnects(self, tmp_path: Path) -> None:
        store = ConversationStore(tmp_path / "conv.db")
        _ = store.conn  # init
        store._conn.close()

        # Should reconnect and succeed
        conv_id = store.create_conversation()
        assert conv_id is not None

    def test_add_message_reconnects(self, tmp_path: Path) -> None:
        store = ConversationStore(tmp_path / "conv.db")
        conv_id = store.create_conversation()

        store._conn.close()

        # Should reconnect and succeed
        store.add_message(conv_id, "user", "hello")
        messages = store.get_recent_messages(conv_id)
        assert len(messages) == 1

    def test_get_conversation_reconnects(self, tmp_path: Path) -> None:
        store = ConversationStore(tmp_path / "conv.db")
        conv_id = store.create_conversation()
        store.add_message(conv_id, "user", "hello")

        store._conn.close()

        conv = store.get_conversation(conv_id)
        assert conv is not None
        assert len(conv.messages) == 1


# ---------------------------------------------------------------------------
# VectorStore tests (mocked ChromaDB)
# ---------------------------------------------------------------------------


class TestVectorStoreReconnect:
    """Verify VectorStore reconnect-on-error pattern."""

    def test_reconnect_clears_client_and_collection(self, tmp_path: Path) -> None:
        from secondbrain.stores.vector import VectorStore

        store = VectorStore(tmp_path / "chroma")
        store._client = MagicMock()
        store._collection = MagicMock()

        store._reconnect()

        assert store._client is None
        assert store._collection is None

    def test_search_reconnects_on_error(self, tmp_path: Path) -> None:
        import numpy as np

        from secondbrain.stores.vector import VectorStore

        store = VectorStore(tmp_path / "chroma")

        # First collection fails on query
        bad_collection = MagicMock()
        bad_collection.query.side_effect = RuntimeError("stale client")

        # Good collection returned after reconnect
        good_collection = MagicMock()
        good_collection.query.return_value = {
            "ids": [["c1"]],
            "distances": [[0.1]],
            "metadatas": [[{"note_path": "test.md", "note_title": "Test"}]],
            "documents": [["hello world"]],
        }

        store._client = MagicMock()
        store._collection = bad_collection

        # After reconnect, the store will call chromadb.PersistentClient()
        # Patch it so we get a mock client that returns the good collection
        mock_new_client = MagicMock()
        mock_new_client.get_or_create_collection.return_value = good_collection

        with patch(
            "secondbrain.stores.vector.chromadb.PersistentClient", return_value=mock_new_client
        ):
            query_emb = np.zeros(384, dtype=np.float32)
            results = store.search(query_emb, top_k=5)

        assert len(results) == 1
        assert results[0][0] == "c1"


class TestVectorStoreDeleteByNotePath:
    """Verify VectorStore.delete_by_note_path with mocked ChromaDB."""

    def test_deletes_matching_chunks(self, tmp_path: Path) -> None:
        from secondbrain.stores.vector import VectorStore

        store = VectorStore(tmp_path / "chroma")

        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": ["c1", "c2"]}
        store._client = MagicMock()
        store._collection = mock_collection

        deleted = store.delete_by_note_path("notes/test.md")
        assert deleted == ["c1", "c2"]
        mock_collection.get.assert_called_once_with(
            where={"note_path": "notes/test.md"},
            include=[],
        )
        mock_collection.delete.assert_called_once_with(ids=["c1", "c2"])

    def test_no_matching_chunks(self, tmp_path: Path) -> None:
        from secondbrain.stores.vector import VectorStore

        store = VectorStore(tmp_path / "chroma")

        mock_collection = MagicMock()
        mock_collection.get.return_value = {"ids": []}
        store._client = MagicMock()
        store._collection = mock_collection

        deleted = store.delete_by_note_path("notes/nonexistent.md")
        assert deleted == []
        mock_collection.delete.assert_not_called()

    def test_reconnects_on_error(self, tmp_path: Path) -> None:
        from secondbrain.stores.vector import VectorStore

        store = VectorStore(tmp_path / "chroma")

        bad_collection = MagicMock()
        bad_collection.get.side_effect = RuntimeError("stale")

        good_collection = MagicMock()
        good_collection.get.return_value = {"ids": ["c1"]}

        store._client = MagicMock()
        store._collection = bad_collection

        mock_new_client = MagicMock()
        mock_new_client.get_or_create_collection.return_value = good_collection

        with patch(
            "secondbrain.stores.vector.chromadb.PersistentClient", return_value=mock_new_client
        ):
            deleted = store.delete_by_note_path("notes/test.md")

        assert deleted == ["c1"]
        good_collection.delete.assert_called_once_with(ids=["c1"])


class TestVectorStoreEpoch:
    """Verify epoch-based invalidation for VectorStore."""

    def test_epoch_triggers_reconnect(self, tmp_path: Path) -> None:
        import time

        from secondbrain.stores.vector import VectorStore

        store = VectorStore(tmp_path / "chroma")
        store._client = MagicMock()
        store._collection = MagicMock()

        # Write initial epoch
        epoch_file = tmp_path / ".reindex_epoch"
        epoch_file.write_text("1")

        # First check sets baseline
        store._check_epoch()
        assert store._client is not None  # not reconnected on first check

        # New epoch
        time.sleep(0.05)
        epoch_file.write_text("2")
        store._last_epoch_check = 0

        store._check_epoch()

        # Should have reconnected
        assert store._client is None
        assert store._collection is None
