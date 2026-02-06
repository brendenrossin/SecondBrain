"""Tests for the index tracker module."""

from pathlib import Path

from secondbrain.stores.index_tracker import IndexTracker


class TestClassifyChanges:
    def test_all_new_on_empty_tracker(self, tmp_path: Path) -> None:
        tracker = IndexTracker(tmp_path / "tracker.db")
        vault_files = {
            "note1.md": (1000.0, "hash1"),
            "note2.md": (1001.0, "hash2"),
        }
        new, modified, deleted, unchanged = tracker.classify_changes(vault_files)
        assert sorted(new) == ["note1.md", "note2.md"]
        assert modified == []
        assert deleted == []
        assert unchanged == []
        tracker.close()

    def test_unchanged_file(self, tmp_path: Path) -> None:
        tracker = IndexTracker(tmp_path / "tracker.db")
        tracker.mark_indexed("note1.md", "hash1", 1000.0, 5)

        vault_files = {"note1.md": (1000.0, "hash1")}
        new, modified, deleted, unchanged = tracker.classify_changes(vault_files)
        assert new == []
        assert modified == []
        assert deleted == []
        assert unchanged == ["note1.md"]
        tracker.close()

    def test_modified_file(self, tmp_path: Path) -> None:
        tracker = IndexTracker(tmp_path / "tracker.db")
        tracker.mark_indexed("note1.md", "hash1", 1000.0, 5)

        # Different mtime AND different hash
        vault_files = {"note1.md": (1001.0, "hash2")}
        new, modified, deleted, unchanged = tracker.classify_changes(vault_files)
        assert new == []
        assert modified == ["note1.md"]
        assert deleted == []
        assert unchanged == []
        tracker.close()

    def test_deleted_file(self, tmp_path: Path) -> None:
        tracker = IndexTracker(tmp_path / "tracker.db")
        tracker.mark_indexed("note1.md", "hash1", 1000.0, 5)
        tracker.mark_indexed("note2.md", "hash2", 1000.0, 3)

        # Only note1 remains in vault
        vault_files = {"note1.md": (1000.0, "hash1")}
        new, modified, deleted, unchanged = tracker.classify_changes(vault_files)
        assert new == []
        assert modified == []
        assert deleted == ["note2.md"]
        assert unchanged == ["note1.md"]
        tracker.close()

    def test_mtime_changed_but_content_same(self, tmp_path: Path) -> None:
        """mtime-only change (e.g., touched) should be classified as unchanged."""
        tracker = IndexTracker(tmp_path / "tracker.db")
        tracker.mark_indexed("note1.md", "hash1", 1000.0, 5)

        # Different mtime, same hash
        vault_files = {"note1.md": (1001.0, "hash1")}
        new, modified, deleted, unchanged = tracker.classify_changes(vault_files)
        assert new == []
        assert modified == []
        assert deleted == []
        assert unchanged == ["note1.md"]
        tracker.close()

    def test_mixed_changes(self, tmp_path: Path) -> None:
        tracker = IndexTracker(tmp_path / "tracker.db")
        tracker.mark_indexed("unchanged.md", "hash_u", 1000.0, 2)
        tracker.mark_indexed("modified.md", "hash_old", 1000.0, 3)
        tracker.mark_indexed("deleted.md", "hash_d", 1000.0, 1)

        vault_files = {
            "unchanged.md": (1000.0, "hash_u"),
            "modified.md": (1001.0, "hash_new"),
            "new.md": (1002.0, "hash_n"),
        }
        new, modified, deleted, unchanged = tracker.classify_changes(vault_files)
        assert new == ["new.md"]
        assert modified == ["modified.md"]
        assert deleted == ["deleted.md"]
        assert unchanged == ["unchanged.md"]
        tracker.close()


class TestTrackerPersistence:
    def test_data_persists_across_instances(self, tmp_path: Path) -> None:
        db_path = tmp_path / "tracker.db"

        tracker1 = IndexTracker(db_path)
        tracker1.mark_indexed("note1.md", "hash1", 1000.0, 5)
        tracker1.close()

        tracker2 = IndexTracker(db_path)
        vault_files = {"note1.md": (1000.0, "hash1")}
        _, _, _, unchanged = tracker2.classify_changes(vault_files)
        assert unchanged == ["note1.md"]
        tracker2.close()

    def test_clear_removes_all(self, tmp_path: Path) -> None:
        tracker = IndexTracker(tmp_path / "tracker.db")
        tracker.mark_indexed("note1.md", "hash1", 1000.0, 5)
        tracker.clear()

        vault_files = {"note1.md": (1000.0, "hash1")}
        new, _, _, _ = tracker.classify_changes(vault_files)
        assert new == ["note1.md"]
        tracker.close()


class TestMarkAndRemove:
    def test_mark_indexed_upserts(self, tmp_path: Path) -> None:
        tracker = IndexTracker(tmp_path / "tracker.db")
        tracker.mark_indexed("note1.md", "hash1", 1000.0, 5)
        tracker.mark_indexed("note1.md", "hash2", 1001.0, 3)

        vault_files = {"note1.md": (1001.0, "hash2")}
        _, _, _, unchanged = tracker.classify_changes(vault_files)
        assert unchanged == ["note1.md"]
        tracker.close()

    def test_remove_file(self, tmp_path: Path) -> None:
        tracker = IndexTracker(tmp_path / "tracker.db")
        tracker.mark_indexed("note1.md", "hash1", 1000.0, 5)
        tracker.remove_file("note1.md")

        vault_files = {"note1.md": (1000.0, "hash1")}
        new, _, _, _ = tracker.classify_changes(vault_files)
        assert new == ["note1.md"]
        tracker.close()


class TestReconnect:
    def test_reconnect_on_closed_connection(self, tmp_path: Path) -> None:
        tracker = IndexTracker(tmp_path / "tracker.db")
        tracker.mark_indexed("note1.md", "hash1", 1000.0, 5)

        # Close connection behind tracker's back
        tracker._conn.close()

        # Should reconnect and succeed
        tracker.mark_indexed("note2.md", "hash2", 1001.0, 3)

        vault_files = {
            "note1.md": (1000.0, "hash1"),
            "note2.md": (1001.0, "hash2"),
        }
        _, _, _, unchanged = tracker.classify_changes(vault_files)
        assert len(unchanged) == 2
        tracker.close()
