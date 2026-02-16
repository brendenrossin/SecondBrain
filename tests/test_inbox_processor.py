"""Tests for the inbox processor module."""

from unittest.mock import MagicMock, patch

from secondbrain.scripts.inbox_processor import (
    _append_to_daily,
    _append_to_existing_note,
    _build_classification_prompt,
    _create_daily_note,
    _ensure_task_category,
    _ensure_task_hierarchy,
    _get_existing_titles,
    _is_duplicate,
    _load_all_sub_projects,
    _move_to_subfolder,
    _normalize_subcategory,
    _route_daily_note,
    _route_living_document,
    _validate_classification,
    _validate_segments,
    _write_tasks_to_daily,
    process_inbox,
)
from secondbrain.settings import DEFAULT_SETTINGS, save_settings


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


class TestGetExistingTitles:
    def test_collects_titles_from_notes_and_concepts(self, tmp_path):
        notes = tmp_path / "10_Notes"
        notes.mkdir()
        (notes / "Alpha.md").write_text("content")
        (notes / "Beta.md").write_text("content")
        concepts = tmp_path / "30_Concepts"
        concepts.mkdir()
        (concepts / "Gamma.md").write_text("content")
        result = _get_existing_titles(tmp_path)
        assert "Alpha" in result
        assert "Beta" in result
        assert "Gamma" in result
        assert "10_Notes/" in result
        assert "30_Concepts/" in result

    def test_caps_at_max_per_folder(self, tmp_path):
        notes = tmp_path / "10_Notes"
        notes.mkdir()
        for i in range(10):
            (notes / f"Note {i}.md").write_text("content")
        result = _get_existing_titles(tmp_path, max_per_folder=3)
        # Should only have 3 titles
        assert result.count("  - ") == 3

    def test_handles_missing_folders(self, tmp_path):
        result = _get_existing_titles(tmp_path)
        assert result == ""

    def test_excludes_projects(self, tmp_path):
        projects = tmp_path / "20_Projects"
        projects.mkdir()
        (projects / "Secret Project.md").write_text("content")
        result = _get_existing_titles(tmp_path)
        assert "Secret Project" not in result


class TestAppendToExistingNote:
    def test_appends_with_date_heading(self, tmp_path):
        notes = tmp_path / "10_Notes"
        notes.mkdir()
        (notes / "My Note.md").write_text(
            "---\ntype: note\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\nOriginal content"
        )
        classification = {
            "existing_note": "My Note",
            "content": "New content to append",
        }
        result = _append_to_existing_note(classification, tmp_path, "10_Notes")
        assert "Appended to 10_Notes/My Note.md" in result
        content = (notes / "My Note.md").read_text()
        assert "Original content" in content
        assert "New content to append" in content
        assert "###" in content  # date heading

    def test_fallback_when_file_missing(self, tmp_path):
        classification = {
            "existing_note": "Nonexistent Note",
            "content": "Some content",
            "suggested_title": "Nonexistent Note",
            "tags": [],
        }
        result = _append_to_existing_note(classification, tmp_path, "10_Notes")
        assert "Created 10_Notes/" in result


class TestValidateClassificationWithExistingNote:
    def test_valid_string(self):
        assert _validate_classification(
            {
                "note_type": "note",
                "existing_note": "My Note",
            }
        )

    def test_valid_null(self):
        assert _validate_classification(
            {
                "note_type": "note",
                "existing_note": None,
            }
        )

    def test_valid_absent(self):
        assert _validate_classification(
            {
                "note_type": "note",
            }
        )

    def test_invalid_type(self):
        assert not _validate_classification(
            {
                "note_type": "note",
                "existing_note": 123,
            }
        )


class TestWriteTasksToDaily:
    def test_creates_new_daily_note(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        classification = {
            "date": "2026-02-15",
            "tasks": [
                {
                    "text": "Buy ring",
                    "category": "Personal",
                    "sub_project": "Rachel",
                    "due_date": "2026-03-31",
                },
                {"text": "Call florist", "category": "Personal", "sub_project": "Rachel"},
            ],
        }
        result = _write_tasks_to_daily(classification, tmp_path)
        assert result is not None
        assert "2 task(s)" in result
        content = (daily_dir / "2026-02-15.md").read_text()
        assert "## Tasks" in content
        assert "- [ ] Buy ring (due: 2026-03-31)" in content
        assert "- [ ] Call florist" in content

    def test_appends_to_existing_daily_note(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        (daily_dir / "2026-02-15.md").write_text(
            "## Focus\n- Focus area\n\n## Notes\n- A note\n\n## Tasks\n### Personal\n- [ ] Existing task\n"
        )
        classification = {
            "date": "2026-02-15",
            "tasks": [{"text": "New task", "category": "Personal"}],
        }
        result = _write_tasks_to_daily(classification, tmp_path)
        assert result is not None
        content = (daily_dir / "2026-02-15.md").read_text()
        assert "- [ ] Existing task" in content
        assert "- [ ] New task" in content

    def test_noop_when_no_tasks(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        classification = {"date": "2026-02-15", "tasks": []}
        result = _write_tasks_to_daily(classification, tmp_path)
        assert result is None
        assert not (daily_dir / "2026-02-15.md").exists()

    def test_noop_when_tasks_missing(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        classification = {"date": "2026-02-15"}
        result = _write_tasks_to_daily(classification, tmp_path)
        assert result is None

    def test_skips_duplicate_tasks(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        (daily_dir / "2026-02-15.md").write_text(
            "## Focus\n- \n\n## Notes\n- \n\n## Tasks\n### Personal\n- [ ] Already here\n"
        )
        classification = {
            "date": "2026-02-15",
            "tasks": [{"text": "Already here", "category": "Personal"}],
        }
        _write_tasks_to_daily(classification, tmp_path)
        content = (daily_dir / "2026-02-15.md").read_text()
        assert content.count("Already here") == 1

    def test_does_not_duplicate_focus_or_notes(self, tmp_path):
        """Verify that _write_tasks_to_daily only writes tasks, not focus/notes items."""
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        (daily_dir / "2026-02-15.md").write_text(
            "## Focus\n- \n\n## Notes\n- \n\n## Tasks\n- [ ] \n"
        )
        classification = {
            "date": "2026-02-15",
            "focus_items": ["Should not appear"],
            "notes_items": ["Also should not appear"],
            "tasks": [{"text": "Real task", "category": "Personal"}],
        }
        _write_tasks_to_daily(classification, tmp_path)
        content = (daily_dir / "2026-02-15.md").read_text()
        assert "Should not appear" not in content
        assert "Also should not appear" not in content
        assert "- [ ] Real task" in content


class TestProcessExistingNoteAlsoWritesTasks:
    @patch("secondbrain.scripts.inbox_processor.LLMClient")
    def test_existing_note_writes_tasks_to_daily(self, mock_llm_cls, tmp_path):
        """Integration test: existing note route writes content AND tasks to daily."""
        # Set up vault structure
        inbox = tmp_path / "Inbox"
        inbox.mkdir()
        notes_dir = tmp_path / "10_Notes"
        notes_dir.mkdir()
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()

        # Create existing note
        (notes_dir / "Engagement Ring.md").write_text(
            "---\ntype: note\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\nOriginal content"
        )

        # Create inbox file
        (inbox / "capture.md").write_text("Some dictated note about the ring")

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm
        mock_llm.chat_json.return_value = {
            "note_type": "note",
            "suggested_title": "Engagement Ring",
            "existing_note": "Engagement Ring",
            "date": "2026-02-15",
            "category": "Personal",
            "sub_project": "Rachel",
            "tags": [],
            "focus_items": [],
            "notes_items": [],
            "tasks": [
                {
                    "text": "Call jeweler",
                    "category": "Personal",
                    "sub_project": "Rachel",
                    "due_date": "2026-03-01",
                },
                {"text": "Set budget", "category": "Personal", "sub_project": "Rachel"},
            ],
            "content": "Updated ring notes from today",
        }

        actions = process_inbox(tmp_path)
        assert len(actions) == 1

        # Content appended to existing note
        note_content = (notes_dir / "Engagement Ring.md").read_text()
        assert "Updated ring notes from today" in note_content

        # Tasks written to daily note
        daily_content = (daily_dir / "2026-02-15.md").read_text()
        assert "- [ ] Call jeweler (due: 2026-03-01)" in daily_content
        assert "- [ ] Set budget" in daily_content


class TestNormalizeSubcategory:
    def test_valid_subcategory_unchanged(self, tmp_path):
        save_settings(tmp_path, DEFAULT_SETTINGS)
        classification = {
            "note_type": "daily_note",
            "tasks": [{"text": "Visit parents", "category": "Personal", "sub_project": "Family"}],
        }
        _normalize_subcategory(classification, tmp_path)
        assert classification["tasks"][0]["sub_project"] == "Family"

    def test_unknown_remaps_to_general(self, tmp_path):
        save_settings(tmp_path, DEFAULT_SETTINGS)
        classification = {
            "note_type": "daily_note",
            "tasks": [
                {"text": "Do stuff", "category": "Personal", "sub_project": "SomeInventedThing"}
            ],
        }
        _normalize_subcategory(classification, tmp_path)
        assert classification["tasks"][0]["sub_project"] == "General"

    def test_category_without_sub_projects_unchanged(self, tmp_path):
        save_settings(tmp_path, DEFAULT_SETTINGS)
        classification = {
            "note_type": "daily_note",
            "tasks": [{"text": "Deploy app", "category": "Work", "sub_project": "AI Receptionist"}],
        }
        _normalize_subcategory(classification, tmp_path)
        assert classification["tasks"][0]["sub_project"] == "AI Receptionist"

    def test_top_level_subcategory_remapped(self, tmp_path):
        save_settings(tmp_path, DEFAULT_SETTINGS)
        classification = {
            "note_type": "note",
            "category": "Personal",
            "sub_project": "BadValue",
            "tasks": [],
        }
        _normalize_subcategory(classification, tmp_path)
        assert classification["sub_project"] == "General"

    def test_top_level_valid_unchanged(self, tmp_path):
        save_settings(tmp_path, DEFAULT_SETTINGS)
        classification = {
            "note_type": "note",
            "category": "Personal",
            "sub_project": "Health",
            "tasks": [],
        }
        _normalize_subcategory(classification, tmp_path)
        assert classification["sub_project"] == "Health"

    def test_top_level_category_without_subs_unchanged(self, tmp_path):
        save_settings(tmp_path, DEFAULT_SETTINGS)
        classification = {
            "note_type": "note",
            "category": "Work",
            "sub_project": "Anything",
            "tasks": [],
        }
        _normalize_subcategory(classification, tmp_path)
        assert classification["sub_project"] == "Anything"

    def test_works_for_any_category_with_sub_projects(self, tmp_path):
        """Normalize works for custom categories, not just Personal."""
        custom = {
            "categories": [
                {"name": "Custom", "sub_projects": {"Alpha": "desc", "General": "fallback"}},
            ]
        }
        save_settings(tmp_path, custom)
        classification = {
            "note_type": "note",
            "tasks": [{"text": "Do thing", "category": "Custom", "sub_project": "Unknown"}],
        }
        _normalize_subcategory(classification, tmp_path)
        assert classification["tasks"][0]["sub_project"] == "General"

    def test_leaves_unknown_when_no_general(self, tmp_path):
        """When no General sub_project exists, leave unknown as-is."""
        custom = {
            "categories": [
                {"name": "Custom", "sub_projects": {"Alpha": "desc"}},
            ]
        }
        save_settings(tmp_path, custom)
        classification = {
            "note_type": "note",
            "tasks": [{"text": "Do thing", "category": "Custom", "sub_project": "Unknown"}],
        }
        _normalize_subcategory(classification, tmp_path)
        assert classification["tasks"][0]["sub_project"] == "Unknown"


class TestDefaultSettingsSubProjects:
    def test_general_fallback_exists(self):
        all_subs = {}
        for cat in DEFAULT_SETTINGS["categories"]:
            if cat.get("sub_projects"):
                all_subs[cat["name"]] = cat["sub_projects"]
        assert "General" in all_subs.get("Personal", {})

    def test_all_expected_subcategories_present(self):
        personal = next(c for c in DEFAULT_SETTINGS["categories"] if c["name"] == "Personal")
        expected = {
            "Family",
            "Rachel",
            "Gifts",
            "Health",
            "Errands",
            "Chores",
            "Projects",
            "General",
        }
        assert set(personal["sub_projects"].keys()) == expected


class TestBuildClassificationPrompt:
    def test_includes_all_categories(self, tmp_path):
        save_settings(tmp_path, DEFAULT_SETTINGS)
        prompt = _build_classification_prompt(tmp_path)
        assert '"Work"' in prompt
        assert '"Personal"' in prompt

    def test_includes_sub_projects(self, tmp_path):
        save_settings(tmp_path, DEFAULT_SETTINGS)
        prompt = _build_classification_prompt(tmp_path)
        assert "Family" in prompt
        assert "Health" in prompt

    def test_includes_custom_categories(self, tmp_path):
        custom = {
            "categories": [
                {"name": "Startup", "sub_projects": {"MVP": "build the mvp"}},
                {"name": "Hobby", "sub_projects": {}},
            ]
        }
        save_settings(tmp_path, custom)
        prompt = _build_classification_prompt(tmp_path)
        assert '"Startup"' in prompt
        assert '"Hobby"' in prompt
        assert "MVP" in prompt


class TestLoadAllSubProjects:
    def test_returns_only_categories_with_subs(self, tmp_path):
        save_settings(tmp_path, DEFAULT_SETTINGS)
        result = _load_all_sub_projects(tmp_path)
        assert "Personal" in result
        assert "Work" not in result  # Work has empty sub_projects

    def test_returns_empty_for_no_subs(self, tmp_path):
        custom = {"categories": [{"name": "Work", "sub_projects": {}}]}
        save_settings(tmp_path, custom)
        result = _load_all_sub_projects(tmp_path)
        assert result == {}
