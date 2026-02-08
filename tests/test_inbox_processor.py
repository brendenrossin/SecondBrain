"""Tests for the inbox processor module."""

from unittest.mock import MagicMock, patch

from secondbrain.scripts.inbox_processor import (
    _append_to_daily,
    _create_daily_note,
    _ensure_task_category,
    _ensure_task_hierarchy,
    _is_duplicate,
    _move_to_subfolder,
    _route_daily_note,
    _route_living_document,
    _validate_classification,
    _validate_segments,
    process_inbox,
)


class TestAppendToDaily:
    def test_appends_focus(self, tmp_path):
        f = tmp_path / "2026-02-05.md"
        f.write_text("## Focus\n- Existing\n\n## Notes\n- Note\n")
        _append_to_daily(f, {"focus_items": ["New focus"], "notes_items": [], "tasks": []})
        content = f.read_text()
        assert "- New focus" in content
        assert content.index("New focus") > content.index("Existing")

    def test_appends_tasks_with_due_date(self, tmp_path):
        f = tmp_path / "2026-02-05.md"
        f.write_text("## Tasks\n### Personal\n- [ ] Existing\n\n## Links\n")
        _append_to_daily(
            f,
            {
                "focus_items": [],
                "notes_items": [],
                "tasks": [{"text": "New task", "category": "Personal", "due_date": "2026-03-01"}],
            },
        )
        content = f.read_text()
        assert "- [ ] New task (due: 2026-03-01)" in content

    def test_appends_tasks_without_due_date(self, tmp_path):
        f = tmp_path / "2026-02-05.md"
        f.write_text("## Tasks\n### Personal\n- [ ] Existing\n\n## Links\n")
        _append_to_daily(
            f,
            {
                "focus_items": [],
                "notes_items": [],
                "tasks": [{"text": "No deadline", "category": "Personal"}],
            },
        )
        content = f.read_text()
        assert "- [ ] No deadline\n" in content
        assert "(due:" not in content.split("No deadline")[1].split("\n")[0]

    def test_skips_duplicate_task(self, tmp_path):
        f = tmp_path / "2026-02-05.md"
        f.write_text("## Tasks\n### Personal\n- [ ] Already here\n")
        _append_to_daily(
            f,
            {
                "focus_items": [],
                "notes_items": [],
                "tasks": [{"text": "Already here", "category": "Personal"}],
            },
        )
        content = f.read_text()
        assert content.count("Already here") == 1


class TestCreateDailyNote:
    def test_creates_with_due_dates(self, tmp_path):
        f = tmp_path / "2026-02-05.md"
        _create_daily_note(
            f,
            {
                "tags": ["personal"],
                "focus_items": ["Focus area"],
                "notes_items": ["A note"],
                "tasks": [
                    {"text": "Task with due", "category": "Personal", "due_date": "2026-03-01"},
                    {"text": "Task no due", "category": "Personal"},
                ],
            },
            "2026-02-05",
        )
        content = f.read_text()
        assert "- [ ] Task with due (due: 2026-03-01)" in content
        assert "- [ ] Task no due\n" in content
        assert "## Focus" in content
        assert "## Tasks" in content


class TestEnsureTaskHierarchy:
    def test_creates_new_hierarchy(self):
        content = "## Tasks\n### AT&T\n- [ ] Existing\n"
        result = _ensure_task_hierarchy(content, "Personal", "Side Project", "- [ ] New")
        assert "### Personal" in result
        assert "#### Side Project" in result
        assert "- [ ] New" in result

    def test_appends_to_existing_category(self):
        content = "## Tasks\n### AT&T\n#### Proj\n- [ ] Old\n"
        result = _ensure_task_hierarchy(content, "AT&T", "Proj", "- [ ] New")
        assert result.count("### AT&T") == 1
        assert result.count("#### Proj") == 1
        assert "- [ ] New" in result


class TestEnsureTaskCategory:
    def test_creates_new_category(self):
        content = "## Tasks\n### AT&T\n- [ ] Old\n"
        result = _ensure_task_category(content, "Personal", "- [ ] New")
        assert "### Personal" in result
        assert "- [ ] New" in result

    def test_appends_to_existing(self):
        content = "## Tasks\n### Personal\n- [ ] Old\n"
        result = _ensure_task_category(content, "Personal", "- [ ] New")
        assert result.count("### Personal") == 1
        assert "- [ ] New" in result


class TestRouteDailyNote:
    def test_creates_new_daily(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        classification = {
            "date": "2026-02-10",
            "tags": ["test"],
            "focus_items": ["Focus"],
            "notes_items": ["Note"],
            "tasks": [{"text": "Task", "category": "Personal", "due_date": "2026-02-15"}],
        }
        result = _route_daily_note(classification, tmp_path)
        assert "Created" in result
        content = (daily_dir / "2026-02-10.md").read_text()
        assert "- [ ] Task (due: 2026-02-15)" in content

    def test_appends_to_existing_daily(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        (daily_dir / "2026-02-05.md").write_text(
            "## Focus\n- Old focus\n\n## Notes\n- Old note\n\n## Tasks\n### Personal\n- [ ] Old\n"
        )
        classification = {
            "date": "2026-02-05",
            "focus_items": [],
            "notes_items": ["New note"],
            "tasks": [{"text": "New task", "category": "Personal"}],
        }
        result = _route_daily_note(classification, tmp_path)
        assert "Appended" in result
        content = (daily_dir / "2026-02-05.md").read_text()
        assert "New note" in content
        assert "New task" in content


class TestProcessInbox:
    def test_empty_inbox(self, tmp_path):
        inbox = tmp_path / "Inbox"
        inbox.mkdir()
        actions = process_inbox(tmp_path)
        assert actions == []

    def test_no_inbox_dir(self, tmp_path):
        actions = process_inbox(tmp_path)
        assert actions == []

    @patch("secondbrain.scripts.inbox_processor.LLMClient")
    def test_processes_and_moves_to_processed(self, mock_llm_cls, tmp_path):
        inbox = tmp_path / "Inbox"
        inbox.mkdir()
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()

        (inbox / "test.md").write_text("I need to do something by Friday")

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
        # Segmentation returns single segment (short text)
        mock_llm.chat_json.return_value = {
            "note_type": "daily_note",
            "date": "2026-02-05",
            "tags": ["test"],
            "focus_items": [],
            "notes_items": [],
            "tasks": [{"text": "Do something", "category": "Personal", "due_date": "2026-02-07"}],
        }

        actions = process_inbox(tmp_path)
        assert len(actions) == 1
        assert "Created" in actions[0] or "Appended" in actions[0]
        assert not (inbox / "test.md").exists()  # inbox file gone from Inbox/
        assert (inbox / "_processed" / "test.md").exists()  # moved to _processed/
        assert (daily_dir / "2026-02-05.md").exists()

        content = (daily_dir / "2026-02-05.md").read_text()
        assert "Do something (due: 2026-02-07)" in content

    @patch("secondbrain.scripts.inbox_processor.LLMClient")
    def test_failed_processing_moves_to_failed(self, mock_llm_cls, tmp_path):
        inbox = tmp_path / "Inbox"
        inbox.mkdir()

        (inbox / "bad.md").write_text("Some bad content")

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
        # Return invalid classification (missing note_type)
        mock_llm.chat_json.return_value = {"invalid": True}

        actions = process_inbox(tmp_path)
        assert len(actions) == 1
        assert "FAILED" in actions[0]
        assert not (inbox / "bad.md").exists()
        assert (inbox / "_failed" / "bad.md").exists()


class TestMoveToSubfolder:
    def test_moves_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("content")
        _move_to_subfolder(f, "_processed")
        assert not f.exists()
        assert (tmp_path / "_processed" / "test.md").exists()

    def test_handles_duplicate_name(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("content")
        dest_dir = tmp_path / "_processed"
        dest_dir.mkdir()
        (dest_dir / "test.md").write_text("existing")
        _move_to_subfolder(f, "_processed")
        assert not f.exists()
        # Original preserved, new file has timestamp suffix
        assert (dest_dir / "test.md").read_text() == "existing"
        files = list(dest_dir.glob("test_*.md"))
        assert len(files) == 1


class TestValidateClassification:
    def test_valid_daily_note(self):
        assert _validate_classification({"note_type": "daily_note", "tasks": []})

    def test_valid_living_document(self):
        assert _validate_classification({"note_type": "living_document"})

    def test_invalid_note_type(self):
        assert not _validate_classification({"note_type": "invalid"})

    def test_not_a_dict(self):
        assert not _validate_classification([1, 2, 3])

    def test_tasks_must_be_list(self):
        assert not _validate_classification({"note_type": "note", "tasks": "not a list"})


class TestValidateSegments:
    def test_valid_segments(self):
        assert _validate_segments([{"content": "text"}])

    def test_invalid_not_list(self):
        assert not _validate_segments({"content": "text"})

    def test_missing_content_field(self):
        assert not _validate_segments([{"topic": "test"}])


class TestDuplicateDetection:
    def test_no_processed_dir(self, tmp_path):
        assert not _is_duplicate("some text", tmp_path)

    def test_detects_duplicate(self, tmp_path):
        inbox = tmp_path / "Inbox"
        processed = inbox / "_processed"
        processed.mkdir(parents=True)
        (processed / "old.md").write_text("same content")
        assert _is_duplicate("same content", tmp_path)

    def test_no_duplicate(self, tmp_path):
        inbox = tmp_path / "Inbox"
        processed = inbox / "_processed"
        processed.mkdir(parents=True)
        (processed / "old.md").write_text("different content")
        assert not _is_duplicate("new content", tmp_path)


class TestRouteLivingDocument:
    def test_creates_new_living_doc(self, tmp_path):
        notes_dir = tmp_path / "10_Notes"
        notes_dir.mkdir()
        classification = {
            "note_type": "living_document",
            "living_doc_name": "Grocery List",
            "content": "- Milk\n- Eggs\n- Bread",
        }
        result = _route_living_document(classification, tmp_path)
        assert "Created living doc" in result
        content = (notes_dir / "Grocery List.md").read_text()
        assert "- Milk" in content
        assert "living_document" in content

    def test_replace_semantics_archives_old(self, tmp_path):
        notes_dir = tmp_path / "10_Notes"
        notes_dir.mkdir()
        # Create existing grocery list
        (notes_dir / "Grocery List.md").write_text(
            "---\ntype: living_document\n---\n- Old item 1\n- Old item 2\n"
        )
        classification = {
            "note_type": "living_document",
            "living_doc_name": "Grocery List",
            "content": "- New item 1\n- New item 2",
        }
        result = _route_living_document(classification, tmp_path)
        assert "Replaced" in result
        assert "archived" in result
        content = (notes_dir / "Grocery List.md").read_text()
        assert "- New item 1" in content
        assert "## Archive" in content
        assert "- Old item 1" in content

    def test_append_semantics(self, tmp_path):
        notes_dir = tmp_path / "10_Notes"
        notes_dir.mkdir()
        (notes_dir / "Recipe Ideas.md").write_text(
            "---\ntype: living_document\n---\nExisting recipes"
        )
        classification = {
            "note_type": "living_document",
            "living_doc_name": "Recipe Ideas",
            "content": "New pasta recipe",
        }
        result = _route_living_document(classification, tmp_path)
        assert "Appended" in result
        content = (notes_dir / "Recipe Ideas.md").read_text()
        assert "Existing recipes" in content
        assert "New pasta recipe" in content
        assert "###" in content  # date heading

    def test_unknown_living_doc_falls_back(self, tmp_path):
        classification = {
            "note_type": "living_document",
            "living_doc_name": "Unknown Doc",
            "content": "Some content",
            "suggested_title": "Unknown",
            "tags": [],
        }
        result = _route_living_document(classification, tmp_path)
        assert "Created 10_Notes/" in result
