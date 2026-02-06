"""Tests for the inbox processor module."""

from unittest.mock import MagicMock, patch

from secondbrain.scripts.inbox_processor import (
    _append_to_daily,
    _create_daily_note,
    _ensure_task_category,
    _ensure_task_hierarchy,
    _route_daily_note,
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
        _append_to_daily(f, {
            "focus_items": [],
            "notes_items": [],
            "tasks": [{"text": "New task", "category": "Personal", "due_date": "2026-03-01"}],
        })
        content = f.read_text()
        assert "- [ ] New task (due: 2026-03-01)" in content

    def test_appends_tasks_without_due_date(self, tmp_path):
        f = tmp_path / "2026-02-05.md"
        f.write_text("## Tasks\n### Personal\n- [ ] Existing\n\n## Links\n")
        _append_to_daily(f, {
            "focus_items": [],
            "notes_items": [],
            "tasks": [{"text": "No deadline", "category": "Personal"}],
        })
        content = f.read_text()
        assert "- [ ] No deadline\n" in content
        assert "(due:" not in content.split("No deadline")[1].split("\n")[0]

    def test_skips_duplicate_task(self, tmp_path):
        f = tmp_path / "2026-02-05.md"
        f.write_text("## Tasks\n### Personal\n- [ ] Already here\n")
        _append_to_daily(f, {
            "focus_items": [],
            "notes_items": [],
            "tasks": [{"text": "Already here", "category": "Personal"}],
        })
        content = f.read_text()
        assert content.count("Already here") == 1


class TestCreateDailyNote:
    def test_creates_with_due_dates(self, tmp_path):
        f = tmp_path / "2026-02-05.md"
        _create_daily_note(f, {
            "tags": ["personal"],
            "focus_items": ["Focus area"],
            "notes_items": ["A note"],
            "tasks": [
                {"text": "Task with due", "category": "Personal", "due_date": "2026-03-01"},
                {"text": "Task no due", "category": "Personal"},
            ],
        }, "2026-02-05")
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
    def test_processes_and_deletes(self, mock_llm_cls, tmp_path):
        inbox = tmp_path / "Inbox"
        inbox.mkdir()
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()

        (inbox / "test.md").write_text("I need to do something by Friday")

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
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
        assert not (inbox / "test.md").exists()  # inbox file deleted
        assert (daily_dir / "2026-02-05.md").exists()

        content = (daily_dir / "2026-02-05.md").read_text()
        assert "Do something (due: 2026-02-07)" in content
