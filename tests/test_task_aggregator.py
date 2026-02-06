"""Tests for the task aggregator module."""

from datetime import datetime, timedelta

from secondbrain.scripts.task_aggregator import (
    AggregatedTask,
    Task,
    _aggregate_tasks,
    _normalize,
    _parse_tasks_from_file,
    _read_aggregate_completions,
    _write_aggregate_file,
    _write_completed_file,
    sync_tasks,
)

# --- Normalize ---


class TestNormalize:
    def test_basic(self):
        assert _normalize("Update Resume") == "update resume"

    def test_strips_punctuation(self):
        assert _normalize("Hello, world!") == "hello world"

    def test_strips_due_date(self):
        assert _normalize("Do the thing (due: 2026-03-01)") == "do the thing"

    def test_collapses_whitespace(self):
        assert _normalize("lots   of    spaces") == "lots of spaces"

    def test_empty(self):
        assert _normalize("") == ""


# --- Parse tasks from file ---


class TestParseTasksFromFile:
    def test_basic_tasks(self, tmp_path):
        md = tmp_path / "2026-02-05.md"
        md.write_text(
            "## Tasks\n"
            "### AT&T\n"
            "#### AI Receptionist\n"
            "- [ ] Build thing\n"
            "- [x] Done thing\n"
            "### Personal\n"
            "- [ ] Buy groceries\n"
        )
        tasks = _parse_tasks_from_file(md, "2026-02-05")
        assert len(tasks) == 3
        assert tasks[0].text == "Build thing"
        assert tasks[0].completed is False
        assert tasks[0].category == "AT&T"
        assert tasks[0].sub_project == "AI Receptionist"
        assert tasks[1].completed is True
        assert tasks[2].category == "Personal"
        assert tasks[2].sub_project == ""

    def test_due_date_extraction(self, tmp_path):
        md = tmp_path / "2026-02-05.md"
        md.write_text(
            "## Tasks\n"
            "### Personal\n"
            "- [ ] Send resume (due: 2026-02-06)\n"
            "- [ ] No deadline task\n"
        )
        tasks = _parse_tasks_from_file(md, "2026-02-05")
        assert len(tasks) == 2
        assert tasks[0].text == "Send resume"
        assert tasks[0].due_date == "2026-02-06"
        assert tasks[1].due_date == ""

    def test_stops_at_next_h2(self, tmp_path):
        md = tmp_path / "2026-02-05.md"
        md.write_text(
            "## Tasks\n"
            "- [ ] Real task\n"
            "## Links surfaced today\n"
            "- [ ] Not a task\n"
        )
        tasks = _parse_tasks_from_file(md, "2026-02-05")
        assert len(tasks) == 1
        assert tasks[0].text == "Real task"

    def test_no_tasks_section(self, tmp_path):
        md = tmp_path / "2026-02-05.md"
        md.write_text("## Notes\n- Just a note\n")
        tasks = _parse_tasks_from_file(md, "2026-02-05")
        assert tasks == []

    def test_indented_subtask_ignored(self, tmp_path):
        """Indented lines under a task (like sub-bullets) should not be parsed as tasks."""
        md = tmp_path / "2026-02-05.md"
        md.write_text(
            "## Tasks\n"
            "### PwC\n"
            "- [ ] Message Agentic AI All Staff chat\n"
            "\t- what we did, how we did it\n"
            "- [ ] Another task\n"
        )
        tasks = _parse_tasks_from_file(md, "2026-02-05")
        assert len(tasks) == 2


# --- Aggregate tasks ---


class TestAggregateTasks:
    def test_groups_same_task(self):
        t1 = Task("Do thing", False, "2026-02-04", "Personal", "", 5)
        t2 = Task("Do thing", False, "2026-02-05", "Personal", "", 5)
        agg = _aggregate_tasks([t1, t2])
        assert len(agg) == 1
        assert len(agg[0].appearances) == 2

    def test_different_categories_separate(self):
        t1 = Task("Do thing", False, "2026-02-04", "AT&T", "", 5)
        t2 = Task("Do thing", False, "2026-02-05", "Personal", "", 5)
        agg = _aggregate_tasks([t1, t2])
        assert len(agg) == 2

    def test_due_date_from_latest(self):
        t1 = Task("Do thing", False, "2026-02-04", "Personal", "", 5, due_date="")
        t2 = Task("Do thing", False, "2026-02-05", "Personal", "", 5, due_date="2026-03-01")
        agg = _aggregate_tasks([t1, t2])
        assert agg[0].due_date == "2026-03-01"


# --- Due label ---


class TestDueLabel:
    def _make_task(self, due_date="", completed=False):
        t = AggregatedTask("Test", "test", "Personal", "", due_date=due_date)
        t.appearances = [Task("Test", completed, "2026-02-05", "Personal", "", 5)]
        return t

    def test_no_due_date(self):
        assert self._make_task().due_label() == ""

    def test_overdue(self):
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        label = self._make_task(due_date=two_days_ago).due_label()
        assert "2 days overdue" in label
        assert "#e03e3e" in label  # red

    def test_yesterday(self):
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        label = self._make_task(due_date=yesterday).due_label()
        assert "1 day overdue" in label
        assert "#e03e3e" in label  # red

    def test_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        label = self._make_task(due_date=today).due_label()
        assert "Today" in label
        assert "#e03e3e" in label  # red

    def test_tomorrow(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        label = self._make_task(due_date=tomorrow).due_label()
        assert "Tomorrow" in label
        assert "#e03e3e" in label  # red

    def test_in_2_days_yellow(self):
        in_2 = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        label = self._make_task(due_date=in_2).due_label()
        assert "in 2 days" in label
        assert "#e8a838" in label  # yellow

    def test_in_3_days_yellow(self):
        in_3 = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        label = self._make_task(due_date=in_3).due_label()
        assert "in 3 days" in label
        assert "#e8a838" in label  # yellow

    def test_in_5_days_blue(self):
        in_5 = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        label = self._make_task(due_date=in_5).due_label()
        assert "in 5 days" in label
        assert "#4dabf7" in label  # blue

    def test_far_future_plain_text(self):
        in_30 = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        label = self._make_task(due_date=in_30).due_label()
        assert "in 30 days" in label
        assert "<span" not in label  # no badge, plain text

    def test_completed_no_label(self):
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert self._make_task(due_date=yesterday, completed=True).due_label() == ""


# --- Read aggregate completions ---


class TestReadAggregateCompletions:
    def test_table_format_open(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        f.write_text(
            "| Status | Task | Added | Due | |\n"
            "|:---:|------|:---:|:---:|:---:|\n"
            "| Open | Open task | [[2026-02-05]] |  |  |\n"
        )
        completions = _read_aggregate_completions(f)
        assert completions[_normalize("Open task")] is False

    def test_table_format_done(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        f.write_text(
            "| Status | Task | Added | Due | |\n"
            "|:---:|------|:---:|:---:|:---:|\n"
            "| Done | Finished task | [[2026-02-05]] |  |  |\n"
        )
        completions = _read_aggregate_completions(f)
        assert completions[_normalize("Finished task")] is True

    def test_table_format_in_progress(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        f.write_text(
            "| Status | Task | Added | Due | |\n"
            "|:---:|------|:---:|:---:|:---:|\n"
            "| In Progress | Working task | [[2026-02-05]] |  |  |\n"
        )
        completions = _read_aggregate_completions(f)
        assert completions[_normalize("Working task")] is False

    def test_list_format(self, tmp_path):
        f = tmp_path / "Completed.md"
        f.write_text(
            "## 2026-02-05\n"
            "- [x] Finished task [[2026-02-05]] *(Personal)*\n"
        )
        completions = _read_aggregate_completions(f)
        assert completions[_normalize("Finished task")] is True

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nope.md"
        assert _read_aggregate_completions(f) == {}


# --- Write aggregate file ---


class TestWriteAggregateFile:
    def test_table_output(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        t = AggregatedTask("Do thing", "do thing", "Personal", "", due_date="2026-03-01")
        t.appearances = [Task("Do thing", False, "2026-02-05", "Personal", "", 5, "2026-03-01")]
        _write_aggregate_file(f, [t])
        content = f.read_text()
        assert "| Open | Do thing |" in content
        assert "| Status | Task | Added | Due |" in content
        assert "2026-03-01" in content
        assert "## Personal" in content

    def test_skips_completed(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        t = AggregatedTask("Done thing", "done thing", "Personal", "")
        t.appearances = [Task("Done thing", True, "2026-02-05", "Personal", "", 5)]
        _write_aggregate_file(f, [t])
        content = f.read_text()
        assert "Done thing" not in content

    def test_no_due_date_empty_column(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        t = AggregatedTask("No deadline", "no deadline", "Personal", "")
        t.appearances = [Task("No deadline", False, "2026-02-05", "Personal", "", 5)]
        _write_aggregate_file(f, [t])
        content = f.read_text()
        # Due column should be empty, last column should be empty
        assert "| Open | No deadline | [[2026-02-05]] |  |  |" in content


# --- Write completed file ---


class TestWriteCompletedFile:
    def test_completed_output(self, tmp_path):
        f = tmp_path / "Completed Tasks.md"
        t = AggregatedTask("Done thing", "done thing", "AT&T", "AI Receptionist")
        t.appearances = [Task("Done thing", True, "2026-02-05", "AT&T", "AI Receptionist", 5)]
        _write_completed_file(f, [t])
        content = f.read_text()
        assert "- [x] Done thing" in content
        assert "*(AT&T > AI Receptionist)*" in content

    def test_no_completed(self, tmp_path):
        f = tmp_path / "Completed Tasks.md"
        t = AggregatedTask("Open thing", "open thing", "Personal", "")
        t.appearances = [Task("Open thing", False, "2026-02-05", "Personal", "", 5)]
        _write_completed_file(f, [t])
        content = f.read_text()
        assert "No completed tasks yet" in content


# --- Full sync integration ---


class TestSyncTasks:
    def _setup_vault(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        tasks_dir = tmp_path / "Tasks"
        tasks_dir.mkdir()

        (daily_dir / "2026-02-04.md").write_text(
            "## Tasks\n"
            "### AT&T\n"
            "- [ ] Old task\n"
            "### Personal\n"
            "- [ ] Buy milk (due: 2026-02-05)\n"
        )
        (daily_dir / "2026-02-05.md").write_text(
            "## Tasks\n"
            "### AT&T\n"
            "- [ ] Old task\n"
            "- [ ] New task\n"
            "### Personal\n"
            "- [x] Buy milk (due: 2026-02-05)\n"
        )
        return tmp_path

    def test_full_sync(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        summary = sync_tasks(vault)
        assert "open" in summary
        assert "completed" in summary

        all_tasks = (vault / "Tasks" / "All Tasks.md").read_text()
        completed = (vault / "Tasks" / "Completed Tasks.md").read_text()

        # Open tasks in table
        assert "Old task" in all_tasks
        assert "New task" in all_tasks
        # Completed task NOT in all tasks
        assert "Buy milk" not in all_tasks
        # Completed task in completed file
        assert "Buy milk" in completed

    def test_bidir_sync_with_done_status(self, tmp_path):
        vault = self._setup_vault(tmp_path)

        # First sync to generate files
        sync_tasks(vault)

        # Now mark "New task" as Done in the Status column
        agg_file = vault / "Tasks" / "All Tasks.md"
        content = agg_file.read_text()
        content = content.replace(
            "| Open | New task |",
            "| Done | New task |",
        )
        agg_file.write_text(content)

        # Re-sync
        summary = sync_tasks(vault)
        assert "daily notes updated" in summary
        assert "0 daily notes updated" not in summary

        # Verify daily note was updated
        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "- [x] New task" in daily

    def test_due_dates_in_table(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        sync_tasks(vault)
        all_tasks = (vault / "Tasks" / "All Tasks.md").read_text()
        assert "|:---:|" in all_tasks
        assert "| Open |" in all_tasks
        assert "| Status |" in all_tasks

    def test_manually_added_due_date_picked_up(self, tmp_path):
        """If a user manually adds (due: ...) to a daily note, sync picks it up."""
        vault = self._setup_vault(tmp_path)
        sync_tasks(vault)

        # Manually add a due date to "Old task" in the daily note
        daily_file = vault / "00_Daily" / "2026-02-05.md"
        content = daily_file.read_text()
        content = content.replace("- [ ] Old task", "- [ ] Old task (due: 2026-02-20)")
        daily_file.write_text(content)

        # Re-sync
        sync_tasks(vault)
        all_tasks = (vault / "Tasks" / "All Tasks.md").read_text()
        assert "2026-02-20" in all_tasks
