"""Tests for the task aggregator module."""

from datetime import datetime, timedelta

from secondbrain.scripts.task_aggregator import (
    AggregatedTask,
    Task,
    _normalize,
    _parse_tasks_from_file,
    _read_aggregate_due_dates,
    _read_aggregate_statuses,
    _write_aggregate_file,
    _write_completed_file,
    aggregate_tasks,
    scan_daily_notes,
    sync_tasks,
    update_task_in_daily,
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
        assert tasks[0].status == "open"
        assert tasks[0].category == "AT&T"
        assert tasks[0].sub_project == "AI Receptionist"
        assert tasks[1].status == "done"
        assert tasks[2].category == "Personal"
        assert tasks[2].sub_project == ""

    def test_in_progress_checkbox(self, tmp_path):
        md = tmp_path / "2026-02-05.md"
        md.write_text(
            "## Tasks\n### Personal\n- [/] Working on it\n- [ ] Not started\n- [x] All done\n"
        )
        tasks = _parse_tasks_from_file(md, "2026-02-05")
        assert len(tasks) == 3
        assert tasks[0].status == "in_progress"
        assert tasks[0].text == "Working on it"
        assert tasks[1].status == "open"
        assert tasks[2].status == "done"

    def test_due_date_extraction(self, tmp_path):
        md = tmp_path / "2026-02-05.md"
        md.write_text(
            "## Tasks\n### Personal\n- [ ] Send resume (due: 2026-02-06)\n- [ ] No deadline task\n"
        )
        tasks = _parse_tasks_from_file(md, "2026-02-05")
        assert len(tasks) == 2
        assert tasks[0].text == "Send resume"
        assert tasks[0].due_date == "2026-02-06"
        assert tasks[1].due_date == ""

    def test_stops_at_next_h2(self, tmp_path):
        md = tmp_path / "2026-02-05.md"
        md.write_text("## Tasks\n- [ ] Real task\n## Links surfaced today\n- [ ] Not a task\n")
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
        t1 = Task("Do thing", "open", "2026-02-04", "Personal", "", 5)
        t2 = Task("Do thing", "open", "2026-02-05", "Personal", "", 5)
        agg = aggregate_tasks([t1, t2])
        assert len(agg) == 1
        assert len(agg[0].appearances) == 2

    def test_different_categories_separate(self):
        t1 = Task("Do thing", "open", "2026-02-04", "AT&T", "", 5)
        t2 = Task("Do thing", "open", "2026-02-05", "Personal", "", 5)
        agg = aggregate_tasks([t1, t2])
        assert len(agg) == 2

    def test_due_date_from_latest(self):
        t1 = Task("Do thing", "open", "2026-02-04", "Personal", "", 5, due_date="")
        t2 = Task("Do thing", "open", "2026-02-05", "Personal", "", 5, due_date="2026-03-01")
        agg = aggregate_tasks([t1, t2])
        assert agg[0].due_date == "2026-03-01"

    def test_status_from_latest_appearance(self):
        t1 = Task("Do thing", "open", "2026-02-04", "Personal", "", 5)
        t2 = Task("Do thing", "in_progress", "2026-02-05", "Personal", "", 5)
        agg = aggregate_tasks([t1, t2])
        assert agg[0].status == "in_progress"
        assert agg[0].completed is False

    def test_completed_from_status(self):
        t1 = Task("Do thing", "open", "2026-02-04", "Personal", "", 5)
        t2 = Task("Do thing", "done", "2026-02-05", "Personal", "", 5)
        agg = aggregate_tasks([t1, t2])
        assert agg[0].status == "done"
        assert agg[0].completed is True


# --- Due label ---


class TestDueLabel:
    def _make_task(self, due_date="", status="open"):
        t = AggregatedTask("Test", "test", "Personal", "", due_date=due_date)
        t.appearances = [Task("Test", status, "2026-02-05", "Personal", "", 5)]
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
        assert self._make_task(due_date=yesterday, status="done").due_label() == ""


# --- Read aggregate statuses ---


class TestReadAggregateStatuses:
    def test_table_format_open(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        f.write_text(
            "| Status | Task | Added | Due | Timeline |\n"
            "|:---:|------|:---:|:---:|:---:|\n"
            "| Open | Open task | [[2026-02-05]] |  |  |\n"
        )
        statuses = _read_aggregate_statuses(f)
        assert statuses[_normalize("Open task")] == "open"

    def test_table_format_done(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        f.write_text(
            "| Status | Task | Added | Due | Timeline |\n"
            "|:---:|------|:---:|:---:|:---:|\n"
            "| Done | Finished task | [[2026-02-05]] |  |  |\n"
        )
        statuses = _read_aggregate_statuses(f)
        assert statuses[_normalize("Finished task")] == "done"

    def test_table_format_in_progress(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        f.write_text(
            "| Status | Task | Added | Due | Timeline |\n"
            "|:---:|------|:---:|:---:|:---:|\n"
            "| In Progress | Working task | [[2026-02-05]] |  |  |\n"
        )
        statuses = _read_aggregate_statuses(f)
        assert statuses[_normalize("Working task")] == "in_progress"

    def test_list_format(self, tmp_path):
        f = tmp_path / "Completed.md"
        f.write_text("## 2026-02-05\n- [x] Finished task [[2026-02-05]] *(Personal)*\n")
        statuses = _read_aggregate_statuses(f)
        assert statuses[_normalize("Finished task")] == "done"

    def test_list_format_in_progress(self, tmp_path):
        f = tmp_path / "Tasks.md"
        f.write_text("- [/] Working on it\n")
        statuses = _read_aggregate_statuses(f)
        assert statuses[_normalize("Working on it")] == "in_progress"

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nope.md"
        assert _read_aggregate_statuses(f) == {}


# --- Write aggregate file ---


class TestWriteAggregateFile:
    def test_table_output(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        t = AggregatedTask("Do thing", "do thing", "Personal", "", due_date="2026-03-01")
        t.appearances = [Task("Do thing", "open", "2026-02-05", "Personal", "", 5, "2026-03-01")]
        _write_aggregate_file(f, [t])
        content = f.read_text()
        assert "| Open | Do thing |" in content
        assert "| Status | Task | Added | Due |" in content
        assert "2026-03-01" in content
        assert "## Personal" in content

    def test_skips_done(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        t = AggregatedTask("Done thing", "done thing", "Personal", "")
        t.appearances = [Task("Done thing", "done", "2026-02-05", "Personal", "", 5)]
        _write_aggregate_file(f, [t])
        content = f.read_text()
        assert "Done thing" not in content

    def test_in_progress_status_column(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        t = AggregatedTask("WIP thing", "wip thing", "Personal", "")
        t.appearances = [Task("WIP thing", "in_progress", "2026-02-05", "Personal", "", 5)]
        _write_aggregate_file(f, [t])
        content = f.read_text()
        assert "| In Progress | WIP thing |" in content

    def test_no_due_date_empty_column(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        t = AggregatedTask("No deadline", "no deadline", "Personal", "")
        t.appearances = [Task("No deadline", "open", "2026-02-05", "Personal", "", 5)]
        _write_aggregate_file(f, [t])
        content = f.read_text()
        # Due column should be empty, last column should be empty
        assert "| Open | No deadline | [[2026-02-05]] |  |  |" in content


# --- Write completed file ---


class TestWriteCompletedFile:
    def test_completed_output(self, tmp_path):
        f = tmp_path / "Completed Tasks.md"
        t = AggregatedTask("Done thing", "done thing", "AT&T", "AI Receptionist")
        t.appearances = [Task("Done thing", "done", "2026-02-05", "AT&T", "AI Receptionist", 5)]
        _write_completed_file(f, [t])
        content = f.read_text()
        assert "- [x] Done thing" in content
        assert "*(AT&T > AI Receptionist)*" in content

    def test_no_completed(self, tmp_path):
        f = tmp_path / "Completed Tasks.md"
        t = AggregatedTask("Open thing", "open thing", "Personal", "")
        t.appearances = [Task("Open thing", "open", "2026-02-05", "Personal", "", 5)]
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
            "## Tasks\n### AT&T\n- [ ] Old task\n### Personal\n- [ ] Buy milk (due: 2026-02-05)\n"
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

    def test_bidir_sync_with_in_progress_status(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        sync_tasks(vault)

        # Mark "New task" as In Progress in the Status column
        agg_file = vault / "Tasks" / "All Tasks.md"
        content = agg_file.read_text()
        content = content.replace(
            "| Open | New task |",
            "| In Progress | New task |",
        )
        agg_file.write_text(content)

        # Re-sync
        sync_tasks(vault)

        # Verify daily note was updated with [/]
        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "- [/] New task" in daily

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


# --- Read aggregate due dates ---


class TestReadAggregateDueDates:
    def test_reads_due_dates_from_table(self, tmp_path):
        f = tmp_path / "All Tasks.md"
        f.write_text(
            "| Status | Task | Added | Due | Timeline |\n"
            "|:---:|------|:---:|:---:|:---:|\n"
            "| Open | Send resume | [[2026-02-05]] | 2026-02-10 | in 4 days |\n"
            "| Open | No deadline | [[2026-02-05]] |  |  |\n"
        )
        due_dates = _read_aggregate_due_dates(f)
        assert due_dates[_normalize("Send resume")] == "2026-02-10"
        assert due_dates[_normalize("No deadline")] == ""

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nope.md"
        assert _read_aggregate_due_dates(f) == {}


# --- Due date sync to daily ---


class TestDueDateSyncToDaily:
    def _setup_vault(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        tasks_dir = tmp_path / "Tasks"
        tasks_dir.mkdir()

        (daily_dir / "2026-02-05.md").write_text(
            "## Tasks\n"
            "### Personal\n"
            "- [ ] Send resume\n"
            "- [ ] Buy groceries (due: 2026-02-10)\n"
            "- [ ] Call dentist (due: 2026-02-08)\n"
        )
        return tmp_path

    def test_sync_new_due_date_to_daily(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        # First sync to generate aggregate
        sync_tasks(vault)

        # Add due date in aggregate
        agg_file = vault / "Tasks" / "All Tasks.md"
        content = agg_file.read_text()
        content = content.replace(
            "| Open | Send resume | [[2026-02-05]] |  |",
            "| Open | Send resume | [[2026-02-05]] | 2026-02-15 |",
        )
        agg_file.write_text(content)

        # Re-sync
        sync_tasks(vault)
        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "(due: 2026-02-15)" in daily
        assert "Send resume (due: 2026-02-15)" in daily

    def test_sync_changed_due_date_to_daily(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        sync_tasks(vault)

        # Change due date in aggregate for "Buy groceries"
        agg_file = vault / "Tasks" / "All Tasks.md"
        content = agg_file.read_text()
        content = content.replace("2026-02-10", "2026-02-20")
        agg_file.write_text(content)

        # Re-sync
        sync_tasks(vault)
        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "(due: 2026-02-20)" in daily
        # Old date should be gone
        assert "(due: 2026-02-10)" not in daily

    def test_empty_aggregate_date_does_not_clear_daily(self, tmp_path):
        """If aggregate has no due date, daily note's due date is preserved."""
        vault = self._setup_vault(tmp_path)
        sync_tasks(vault)

        # Aggregate has date for "Call dentist". Verify it's in daily after sync.
        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "(due: 2026-02-08)" in daily
        assert "Call dentist" in daily

    def test_due_date_round_trip(self, tmp_path):
        """Add due date in daily -> aggregate -> change in aggregate -> back to daily."""
        vault = self._setup_vault(tmp_path)

        # Step 1: Sync (Send resume has no due date)
        sync_tasks(vault)

        # Step 2: Add due date in daily note
        daily_file = vault / "00_Daily" / "2026-02-05.md"
        content = daily_file.read_text()
        content = content.replace("- [ ] Send resume", "- [ ] Send resume (due: 2026-03-01)")
        daily_file.write_text(content)

        # Step 3: Re-sync -> aggregate should pick it up
        sync_tasks(vault)
        agg = (vault / "Tasks" / "All Tasks.md").read_text()
        assert "2026-03-01" in agg

        # Step 4: Change due date in aggregate
        agg_file = vault / "Tasks" / "All Tasks.md"
        content = agg_file.read_text()
        content = content.replace("2026-03-01", "2026-03-15")
        agg_file.write_text(content)

        # Step 5: Re-sync -> daily should have new date
        sync_tasks(vault)
        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "(due: 2026-03-15)" in daily
        assert "(due: 2026-03-01)" not in daily


# --- Update task in daily ---


class TestUpdateTaskInDaily:
    def _setup_vault(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        (daily_dir / "2026-02-05.md").write_text(
            "## Tasks\n### Personal\n- [ ] Send resume\n- [/] Working on report\n- [x] Done thing\n"
        )
        return tmp_path

    def test_mark_open_as_done(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        result = update_task_in_daily(vault, "Send resume", "Personal", "", status="done")
        assert result is not None
        assert result.status == "done"
        assert result.completed is True
        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "- [x] Send resume" in daily

    def test_mark_done_as_open(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        result = update_task_in_daily(vault, "Done thing", "Personal", "", status="open")
        assert result is not None
        assert result.status == "open"
        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "- [ ] Done thing" in daily

    def test_mark_open_as_in_progress(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        result = update_task_in_daily(vault, "Send resume", "Personal", "", status="in_progress")
        assert result is not None
        assert result.status == "in_progress"
        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "- [/] Send resume" in daily

    def test_add_due_date(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        result = update_task_in_daily(vault, "Send resume", "Personal", "", due_date="2026-03-01")
        assert result is not None
        assert result.due_date == "2026-03-01"
        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "Send resume (due: 2026-03-01)" in daily

    def test_remove_due_date(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        (daily_dir / "2026-02-05.md").write_text(
            "## Tasks\n### Personal\n- [ ] Send resume (due: 2026-03-01)\n"
        )
        result = update_task_in_daily(tmp_path, "Send resume", "Personal", "", due_date="")
        assert result is not None
        assert result.due_date == ""
        daily = (daily_dir / "2026-02-05.md").read_text()
        assert "(due:" not in daily

    def test_task_not_found(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        result = update_task_in_daily(vault, "Nonexistent task", "Personal", "", status="done")
        assert result is None

    def test_regenerates_aggregate_files(self, tmp_path):
        """update_task_in_daily should regenerate aggregate files so sync doesn't revert."""
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        tasks_dir = tmp_path / "Tasks"
        tasks_dir.mkdir()
        (daily_dir / "2026-02-05.md").write_text(
            "## Tasks\n### Personal\n- [ ] Send resume\n- [ ] Buy milk\n"
        )
        # First sync to create aggregate files
        sync_tasks(tmp_path)
        agg_before = (tasks_dir / "All Tasks.md").read_text()
        assert "| Open | Send resume |" in agg_before

        # Update via API (mark as done)
        result = update_task_in_daily(tmp_path, "Send resume", "Personal", "", status="done")
        assert result is not None
        assert result.status == "done"

        # Aggregate files should be updated immediately (not stale)
        agg_after = (tasks_dir / "All Tasks.md").read_text()
        assert "Send resume" not in agg_after  # done tasks not in All Tasks
        completed = (tasks_dir / "Completed Tasks.md").read_text()
        assert "Send resume" in completed

        # Now run sync again — should NOT revert the change
        sync_tasks(tmp_path)
        daily = (daily_dir / "2026-02-05.md").read_text()
        assert "- [x] Send resume" in daily  # still done, not reverted


# --- Category reassignment ---


class TestCategoryReassignment:
    def _setup_vault(self, tmp_path):
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        tasks_dir = tmp_path / "Tasks"
        tasks_dir.mkdir()
        (daily_dir / "2026-02-05.md").write_text(
            "## Tasks\n"
            "### AT&T\n"
            "#### AI Receptionist\n"
            "- [ ] Build prototype\n"
            "- [ ] Write docs\n"
            "### Personal\n"
            "- [ ] Buy groceries\n"
            "## Notes\n"
            "Some notes here\n"
        )
        return tmp_path

    def test_move_to_existing_category(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        result = update_task_in_daily(
            vault,
            "Build prototype",
            "AT&T",
            "AI Receptionist",
            new_category="Personal",
            new_sub_project="",
        )
        assert result is not None
        assert result.category == "Personal"
        assert result.sub_project == ""

        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        # Task should be under Personal, not AT&T > AI Receptionist
        lines = daily.split("\n")
        personal_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "### Personal")
        # Find the task after Personal heading
        found = False
        for i in range(personal_idx + 1, len(lines)):
            if lines[i].strip().startswith("### ") or lines[i].strip().startswith("## "):
                break
            if "Build prototype" in lines[i]:
                found = True
                break
        assert found, "Task should be under ### Personal"

    def test_move_to_new_category(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        result = update_task_in_daily(
            vault,
            "Buy groceries",
            "Personal",
            "",
            new_category="Health",
            new_sub_project="",
        )
        assert result is not None
        assert result.category == "Health"

        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "### Health" in daily
        # Task should be under Health
        lines = daily.split("\n")
        health_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "### Health")
        found = False
        for i in range(health_idx + 1, len(lines)):
            if lines[i].strip().startswith("### ") or lines[i].strip().startswith("## "):
                break
            if "Buy groceries" in lines[i]:
                found = True
                break
        assert found, "Task should be under ### Health"

    def test_move_to_new_sub_project(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        result = update_task_in_daily(
            vault,
            "Buy groceries",
            "Personal",
            "",
            new_category="AT&T",
            new_sub_project="Billing",
        )
        assert result is not None
        assert result.category == "AT&T"
        assert result.sub_project == "Billing"

        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        assert "#### Billing" in daily
        lines = daily.split("\n")
        billing_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "#### Billing")
        found = False
        for i in range(billing_idx + 1, len(lines)):
            if (
                lines[i].strip().startswith("#### ")
                or lines[i].strip().startswith("### ")
                or lines[i].strip().startswith("## ")
            ):
                break
            if "Buy groceries" in lines[i]:
                found = True
                break
        assert found, "Task should be under #### Billing"

    def test_move_from_sub_project_to_no_sub_project(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        result = update_task_in_daily(
            vault,
            "Build prototype",
            "AT&T",
            "AI Receptionist",
            new_category="AT&T",
            new_sub_project="",
        )
        assert result is not None
        assert result.category == "AT&T"
        assert result.sub_project == ""

        daily = (vault / "00_Daily" / "2026-02-05.md").read_text()
        lines = daily.split("\n")
        # Task should be under ### AT&T but NOT under #### AI Receptionist
        att_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "### AT&T")
        ai_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "#### AI Receptionist")
        # Find task between ### AT&T and #### AI Receptionist
        found_before_sub = False
        for i in range(att_idx + 1, ai_idx):
            if "Build prototype" in lines[i]:
                found_before_sub = True
                break
        assert found_before_sub, "Task should be directly under ### AT&T, before #### sub-heading"

    def test_multi_appearance_all_notes_updated(self, tmp_path):
        """Moving a task's category should update ALL daily notes, not just the latest."""
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        tasks_dir = tmp_path / "Tasks"
        tasks_dir.mkdir()

        # Task appears in two daily notes under Personal
        (daily_dir / "2026-02-04.md").write_text("## Tasks\n### Personal\n- [ ] Send resume\n")
        (daily_dir / "2026-02-05.md").write_text("## Tasks\n### Personal\n- [ ] Send resume\n")

        result = update_task_in_daily(
            tmp_path,
            "Send resume",
            "Personal",
            "",
            new_category="Job Search",
            new_sub_project="",
        )
        assert result is not None
        assert result.category == "Job Search"

        # Both daily notes should be updated
        daily_04 = (daily_dir / "2026-02-04.md").read_text()
        daily_05 = (daily_dir / "2026-02-05.md").read_text()
        assert "### Job Search" in daily_04
        assert "### Job Search" in daily_05
        assert "Send resume" in daily_04
        assert "Send resume" in daily_05

        # Should NOT have duplicate aggregated entries
        all_tasks = scan_daily_notes(daily_dir)
        agg = aggregate_tasks(all_tasks)
        matching = [a for a in agg if a.normalized == _normalize("Send resume")]
        assert len(matching) == 1, "Should be one aggregated entry, not duplicates"
        assert matching[0].category == "Job Search"
        assert len(matching[0].appearances) == 2

    def test_combined_category_and_status_change(self, tmp_path):
        """Category reassignment + status change in a single call should both work."""
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir()
        tasks_dir = tmp_path / "Tasks"
        tasks_dir.mkdir()

        (daily_dir / "2026-02-05.md").write_text(
            "## Tasks\n### Personal\n- [ ] Send resume\n### Work\n- [ ] Other task\n"
        )

        result = update_task_in_daily(
            tmp_path,
            "Send resume",
            "Personal",
            "",
            status="in_progress",
            new_category="Work",
            new_sub_project="",
        )
        assert result is not None
        assert result.category == "Work"
        assert result.status == "in_progress"

        daily = (daily_dir / "2026-02-05.md").read_text()
        assert "- [/] Send resume" in daily
        # Task should be under Work, not Personal
        lines = daily.split("\n")
        work_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "### Work")
        found = False
        for i in range(work_idx + 1, len(lines)):
            if lines[i].strip().startswith("### ") or lines[i].strip().startswith("## "):
                break
            if "Send resume" in lines[i]:
                found = True
                break
        assert found, "Task should be under ### Work with in_progress status"

    def test_aggregate_files_reflect_new_category(self, tmp_path):
        vault = self._setup_vault(tmp_path)
        # Initial sync
        sync_tasks(vault)

        result = update_task_in_daily(
            vault,
            "Build prototype",
            "AT&T",
            "AI Receptionist",
            new_category="Personal",
            new_sub_project="",
        )
        assert result is not None

        agg = (vault / "Tasks" / "All Tasks.md").read_text()
        # Task should appear under Personal in the aggregate
        assert "## Personal" in agg
        # Find "Build prototype" and verify it's under Personal, not AT&T
        lines = agg.split("\n")
        personal_section = False
        found_in_personal = False
        for line in lines:
            if line.strip() == "## Personal":
                personal_section = True
            elif line.strip().startswith("## ") and personal_section:
                personal_section = False
            if personal_section and "Build prototype" in line:
                found_in_personal = True
                break
        assert found_in_personal, "Aggregate should show task under Personal"
