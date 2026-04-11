"""Task parser edge case tests — gaps identified by TraceEval."""

from pathlib import Path

from secondbrain.scripts.task_aggregator import (
    Task,
    _parse_tasks_from_file,
    aggregate_tasks,
    scan_daily_notes,
)


class TestMalformedTaskLines:
    def test_line_without_checkbox_skipped(self, tmp_path: Path):
        md = tmp_path / "2026-03-01.md"
        md.write_text("## Tasks\n### Work\n- Just a note\n- [ ] Real task\n")
        tasks = _parse_tasks_from_file(md, "2026-03-01")
        assert len(tasks) == 1
        assert tasks[0].text == "Real task"

    def test_incomplete_checkbox_skipped(self, tmp_path: Path):
        md = tmp_path / "2026-03-01.md"
        md.write_text("## Tasks\n### Work\n- [x Broken\n- [ ] Valid task\n")
        tasks = _parse_tasks_from_file(md, "2026-03-01")
        assert len(tasks) == 1
        assert tasks[0].text == "Valid task"

    def test_empty_task_text_skipped(self, tmp_path: Path):
        md = tmp_path / "2026-03-01.md"
        md.write_text("## Tasks\n### Work\n- [ ] \n- [ ] Non-empty task\n")
        tasks = _parse_tasks_from_file(md, "2026-03-01")
        assert len(tasks) == 1
        assert tasks[0].text == "Non-empty task"

    def test_uppercase_x_is_done(self, tmp_path: Path):
        md = tmp_path / "2026-03-01.md"
        md.write_text("## Tasks\n### Work\n- [X] Done with uppercase X\n")
        tasks = _parse_tasks_from_file(md, "2026-03-01")
        assert len(tasks) == 1
        assert tasks[0].status == "done"
        assert tasks[0].text == "Done with uppercase X"


class TestEmptyAndMissingSections:
    def test_empty_tasks_section(self, tmp_path: Path):
        md = tmp_path / "2026-03-01.md"
        md.write_text("## Tasks\n\n## Notes\n- Something here\n")
        tasks = _parse_tasks_from_file(md, "2026-03-01")
        assert tasks == []

    def test_file_with_no_tasks_heading(self, tmp_path: Path):
        md = tmp_path / "2026-03-01.md"
        md.write_text("## Notes\n- Just a note\n## Links\n- [ ] Not a task section\n")
        tasks = _parse_tasks_from_file(md, "2026-03-01")
        assert tasks == []


class TestCategorySubProjectTracking:
    def test_tasks_before_any_category_have_empty_category(self, tmp_path: Path):
        md = tmp_path / "2026-03-01.md"
        md.write_text("## Tasks\n- [ ] Uncategorized task\n### Work\n- [ ] Categorized task\n")
        tasks = _parse_tasks_from_file(md, "2026-03-01")
        assert len(tasks) == 2
        assert tasks[0].text == "Uncategorized task"
        assert tasks[0].category == ""
        assert tasks[1].category == "Work"

    def test_sub_project_resets_on_new_category(self, tmp_path: Path):
        md = tmp_path / "2026-03-01.md"
        md.write_text(
            "## Tasks\n"
            "### Work\n"
            "#### Sub Project A\n"
            "- [ ] Task in sub project\n"
            "### Personal\n"
            "- [ ] Task without sub project\n"
        )
        tasks = _parse_tasks_from_file(md, "2026-03-01")
        assert len(tasks) == 2
        assert tasks[0].sub_project == "Sub Project A"
        assert tasks[1].category == "Personal"
        assert tasks[1].sub_project == ""


class TestScanDailyNotes:
    def test_scans_multiple_files_sorted(self, tmp_path: Path):
        # Two valid date files and one non-date file
        (tmp_path / "2026-03-01.md").write_text("## Tasks\n### Work\n- [ ] Task from March 1\n")
        (tmp_path / "2026-03-02.md").write_text("## Tasks\n### Work\n- [ ] Task from March 2\n")
        (tmp_path / "not-a-date.md").write_text("## Tasks\n### Work\n- [ ] Should be skipped\n")

        tasks = scan_daily_notes(tmp_path)
        # Only the two date-named files should be scanned
        assert len(tasks) == 2
        dates = [t.source_date for t in tasks]
        assert "2026-03-01" in dates
        assert "2026-03-02" in dates
        # Tasks sorted by filename (alphabetical = chronological for ISO dates)
        assert tasks[0].source_date == "2026-03-01"
        assert tasks[1].source_date == "2026-03-02"

    def test_nonexistent_directory_returns_empty(self, tmp_path: Path):
        missing = tmp_path / "does_not_exist"
        tasks = scan_daily_notes(missing)
        assert tasks == []


class TestDueDateEdgeCases:
    def test_due_date_stripped_from_task_text(self, tmp_path: Path):
        md = tmp_path / "2026-03-01.md"
        md.write_text("## Tasks\n### Work\n- [ ] Submit report (due: 2026-03-15)\n")
        tasks = _parse_tasks_from_file(md, "2026-03-01")
        assert len(tasks) == 1
        assert tasks[0].text == "Submit report"
        assert tasks[0].due_date == "2026-03-15"

    def test_aggregation_uses_latest_due_date(self, tmp_path: Path):
        # Same task appears in two files; later file has a later due date
        (tmp_path / "2026-03-01.md").write_text(
            "## Tasks\n### Work\n- [ ] Submit report (due: 2026-03-10)\n"
        )
        (tmp_path / "2026-03-02.md").write_text(
            "## Tasks\n### Work\n- [ ] Submit report (due: 2026-03-20)\n"
        )
        all_tasks = scan_daily_notes(tmp_path)
        aggregated = aggregate_tasks(all_tasks)
        assert len(aggregated) == 1
        # aggregate_tasks updates due_date when a later appearance has one
        assert aggregated[0].due_date == "2026-03-20"

    def test_aggregation_keeps_due_date_from_earlier_if_later_has_none(self, tmp_path: Path):
        # First appearance has due date; second appearance has no due date
        (tmp_path / "2026-03-01.md").write_text(
            "## Tasks\n### Work\n- [ ] Submit report (due: 2026-03-10)\n"
        )
        (tmp_path / "2026-03-02.md").write_text(
            "## Tasks\n### Work\n- [ ] Submit report\n"
        )
        all_tasks = scan_daily_notes(tmp_path)
        aggregated = aggregate_tasks(all_tasks)
        assert len(aggregated) == 1
        # Later appearance has no due date, so the earlier due date should be kept
        assert aggregated[0].due_date == "2026-03-10"
