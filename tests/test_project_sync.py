"""Tests for the project sync module."""

from secondbrain.scripts.project_sync import (
    AUTO_END,
    AUTO_START,
    _build_task_table,
    _extract_daily_notes_mentions,
    _update_auto_section,
    match_project,
    normalize_project_name,
    sync_projects,
)
from secondbrain.scripts.task_aggregator import AggregatedTask, Task


class TestNormalizeProjectName:
    def test_strips_md_extension(self):
        assert normalize_project_name("SecondBrain.md") == "secondbrain"

    def test_lowercases(self):
        assert normalize_project_name("MyProject") == "myproject"

    def test_strips_punctuation(self):
        assert normalize_project_name("AI-Receptionist") == "aireceptionist"

    def test_removes_whitespace(self):
        assert normalize_project_name("Second   Brain") == "secondbrain"

    def test_empty(self):
        assert normalize_project_name("") == ""


class TestMatchProject:
    def test_exact_match(self):
        assert match_project("SecondBrain.md", "SecondBrain") is True

    def test_sub_project_substring(self):
        assert match_project("SecondBrain.md", "Second Brain") is True

    def test_project_in_sub(self):
        assert match_project("AI Receptionist.md", "AI Receptionist MVP") is True

    def test_no_match(self):
        assert match_project("SecondBrain.md", "Totally Different") is False

    def test_empty_sub_project(self):
        assert match_project("SecondBrain.md", "") is False


class TestExtractDailyNotesMentions:
    def test_finds_mentions_in_notes_section(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        (daily_dir / "2026-02-05.md").write_text(
            "## Notes\n"
            "- Worked on SecondBrain indexing today\n"
            "- Had lunch\n"
            "## Tasks\n"
            "- [ ] Something\n"
        )
        mentions = _extract_daily_notes_mentions(daily_dir, "SecondBrain")
        assert len(mentions) == 1
        assert mentions[0][0] == "2026-02-05"
        assert "SecondBrain" in mentions[0][1]

    def test_ignores_non_bullet_lines(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        (daily_dir / "2026-02-05.md").write_text(
            "## Notes\n"
            "SecondBrain stuff (not a bullet)\n"
        )
        mentions = _extract_daily_notes_mentions(daily_dir, "SecondBrain")
        assert len(mentions) == 0

    def test_respects_date_cutoff(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        # Old note (beyond 30 days)
        (daily_dir / "2025-01-01.md").write_text(
            "## Notes\n"
            "- Old SecondBrain note\n"
        )
        mentions = _extract_daily_notes_mentions(daily_dir, "SecondBrain", days=30)
        assert len(mentions) == 0

    def test_empty_dir(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        assert _extract_daily_notes_mentions(daily_dir, "SecondBrain") == []


class TestUpdateAutoSection:
    def test_inserts_new_section(self):
        content = "# My Project\n\nSome content.\n"
        result = _update_auto_section(content, "## Open Tasks", ["line1", "line2"])
        assert "## Open Tasks" in result
        assert AUTO_START in result
        assert "line1\nline2" in result
        assert AUTO_END in result
        # Original content preserved
        assert "# My Project" in result
        assert "Some content." in result

    def test_updates_existing_section(self):
        content = (
            "# My Project\n\n"
            "## Open Tasks\n"
            f"{AUTO_START}\n"
            "old content\n"
            f"{AUTO_END}\n\n"
            "## Other Section\n"
        )
        result = _update_auto_section(content, "## Open Tasks", ["new content"])
        assert "old content" not in result
        assert "new content" in result
        assert "## Other Section" in result

    def test_preserves_content_after_section(self):
        content = (
            "## Open Tasks\n"
            f"{AUTO_START}\n"
            "old\n"
            f"{AUTO_END}\n"
            "\nManual notes below.\n"
        )
        result = _update_auto_section(content, "## Open Tasks", ["new"])
        assert "Manual notes below." in result
        assert "new" in result


class TestBuildTaskTable:
    def test_empty_tasks(self):
        lines = _build_task_table([])
        assert any("No matching" in line for line in lines)

    def test_builds_table(self):
        t = AggregatedTask("Do thing", "do thing", "Personal", "SecondBrain", due_date="2026-03-01")
        t.appearances = [Task("Do thing", False, "2026-02-05", "Personal", "SecondBrain", 5, "2026-03-01")]
        lines = _build_task_table([t])
        joined = "\n".join(lines)
        assert "| Status | Task | Added | Due | Timeline |" in joined
        assert "| Open | Do thing |" in joined


class TestSyncProjects:
    def _setup_vault(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        projects_dir = tmp_path / "20_Projects"
        projects_dir.mkdir()
        tasks_dir = tmp_path / "Tasks"
        tasks_dir.mkdir()

        (daily_dir / "2026-02-05.md").write_text(
            "## Tasks\n"
            "### PwC\n"
            "#### SecondBrain\n"
            "- [ ] Add incremental indexing\n"
            "- [ ] Fix search ranking\n"
            "### Personal\n"
            "- [ ] Buy groceries\n"
            "## Notes\n"
            "- Worked on SecondBrain vector store today\n"
            "- Had a meeting about PwC\n"
        )

        (projects_dir / "SecondBrain.md").write_text(
            "# SecondBrain\n\nProject for personal knowledge management.\n"
        )

        return tmp_path

    def test_creates_sections(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        summary = sync_projects(vault)
        assert "1 project files updated" in summary

        content = (vault / "20_Projects" / "SecondBrain.md").read_text()
        assert "## Open Tasks" in content
        assert "Add incremental indexing" in content
        assert "Fix search ranking" in content
        assert AUTO_START in content
        assert AUTO_END in content

    def test_updates_existing_sections(self, tmp_path):
        vault = self._setup_vault(tmp_path)

        # First sync
        sync_projects(vault)

        # Second sync should update (not duplicate)
        sync_projects(vault)
        content = (vault / "20_Projects" / "SecondBrain.md").read_text()
        assert content.count("## Open Tasks") == 1
        assert content.count(AUTO_START) == 2  # one per section

    def test_no_projects_dir(self, tmp_path):
        summary = sync_projects(tmp_path)
        assert "No 20_Projects" in summary

    def test_no_matching_tasks(self, tmp_path):
        projects_dir = tmp_path / "20_Projects"
        projects_dir.mkdir()
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()

        (projects_dir / "UnrelatedProject.md").write_text("# Unrelated\n")
        (daily_dir / "2026-02-05.md").write_text(
            "## Tasks\n### Personal\n- [ ] Buy milk\n"
        )

        summary = sync_projects(tmp_path)
        assert "0 project files updated" in summary

    def test_preserves_manual_content(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        project_file = vault / "20_Projects" / "SecondBrain.md"

        # Add manual content to project file
        project_file.write_text(
            "# SecondBrain\n\n"
            "My manual notes about this project.\n\n"
            "## Architecture\n\nSome architecture details.\n"
        )

        sync_projects(vault)
        content = project_file.read_text()
        assert "My manual notes about this project." in content
        assert "## Architecture" in content
        assert "Some architecture details." in content

    def test_with_precomputed_tasks(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        t = AggregatedTask("Test task", "test task", "PwC", "SecondBrain")
        t.appearances = [Task("Test task", False, "2026-02-05", "PwC", "SecondBrain", 5)]

        summary = sync_projects(vault, aggregated_tasks=[t])
        assert "1 project files updated" in summary

    def test_recent_notes_section(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        sync_projects(vault)

        content = (vault / "20_Projects" / "SecondBrain.md").read_text()
        assert "## Recent Notes" in content
        assert "SecondBrain vector store" in content
