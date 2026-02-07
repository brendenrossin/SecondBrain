"""Task aggregator: scans daily notes for tasks, builds aggregated view with bi-dir sync."""

import logging
import re
import string
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Due date pattern in daily notes: (due: YYYY-MM-DD)
DUE_DATE_RE = re.compile(r"\s*\(due:\s*(\d{4}-\d{2}-\d{2})\)\s*$")

BADGE_STYLE = "padding:2px 8px;border-radius:4px;font-size:0.85em;color:white"


def _badge(text: str, color: str) -> str:
    """Create an HTML badge span for Obsidian reading mode."""
    return f'<span style="background:{color};{BADGE_STYLE}">{text}</span>'


@dataclass
class Task:
    """A single task extracted from a daily note."""

    text: str
    completed: bool
    source_date: str  # YYYY-MM-DD
    category: str  # e.g. "AT&T", "PwC", "Personal"
    sub_project: str  # e.g. "AI Receptionist", "" for none
    line_number: int  # line index in source file
    due_date: str = ""  # YYYY-MM-DD or empty
    normalized: str = ""  # set in __post_init__

    def __post_init__(self) -> None:
        self.normalized = _normalize(self.text)


@dataclass
class AggregatedTask:
    """A task with all its appearances across daily notes."""

    text: str
    normalized: str
    category: str
    sub_project: str
    due_date: str = ""
    appearances: list[Task] = field(default_factory=list)

    @property
    def completed(self) -> bool:
        """Task is completed if its most recent appearance is completed."""
        if not self.appearances:
            return False
        return self.appearances[-1].completed

    @property
    def first_date(self) -> str:
        return self.appearances[0].source_date if self.appearances else ""

    @property
    def latest_date(self) -> str:
        return self.appearances[-1].source_date if self.appearances else ""

    @property
    def days_open(self) -> int:
        if self.completed or not self.first_date:
            return 0
        first = datetime.strptime(self.first_date, "%Y-%m-%d")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return (today - first).days

    def due_label(self) -> str:
        """Return a label for the due date column: 'in X days', 'Today', etc."""
        if not self.due_date or self.completed:
            return ""
        try:
            due = datetime.strptime(self.due_date, "%Y-%m-%d")
        except ValueError:
            return ""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        days_until = (due - today).days

        # Build the text
        if days_until < -1:
            text = f"{abs(days_until)} days overdue"
        elif days_until == -1:
            text = "1 day overdue"
        elif days_until == 0:
            text = "Today"
        elif days_until == 1:
            text = "Tomorrow"
        else:
            text = f"in {days_until} days"

        # Apply color badge based on urgency
        if days_until <= 1:  # overdue, today, or tomorrow
            return _badge(text, "#e03e3e")
        if days_until <= 3:
            return _badge(text, "#e8a838")
        if days_until <= 7:
            return _badge(text, "#4dabf7")
        return text


def sync_tasks(vault_path: Path) -> str:
    """Run the full task aggregation and bi-directional sync.

    Returns a summary of actions taken.
    """
    daily_dir = vault_path / "00_Daily"
    tasks_dir = vault_path / "Tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    aggregate_file = tasks_dir / "All Tasks.md"
    completed_file = tasks_dir / "Completed Tasks.md"

    # Step 1: Read existing states from both files (for bi-dir sync)
    existing_completions = _read_aggregate_completions(aggregate_file)
    existing_completions.update(_read_aggregate_completions(completed_file))
    existing_due_dates = _read_aggregate_due_dates(aggregate_file)

    # Step 2: Scan daily notes for all tasks
    all_tasks = scan_daily_notes(daily_dir)

    # Step 3: Bi-directional sync — push completions + due dates from aggregate back to daily notes
    updates = _sync_changes_to_daily(daily_dir, all_tasks, existing_completions, existing_due_dates)

    # Step 4: Re-scan daily notes after sync (picks up any changes)
    if updates > 0:
        all_tasks = scan_daily_notes(daily_dir)

    # Step 5: Aggregate tasks by normalized text
    aggregated = aggregate_tasks(all_tasks)

    # Step 6: Generate the aggregate files (open + completed separately)
    _write_aggregate_file(aggregate_file, aggregated)
    _write_completed_file(completed_file, aggregated)

    open_count = sum(1 for t in aggregated if not t.completed)
    done_count = sum(1 for t in aggregated if t.completed)
    return f"Synced tasks: {open_count} open, {done_count} completed, {updates} daily notes updated"


def _normalize(text: str) -> str:
    """Normalize task text for matching: lowercase, strip punctuation and whitespace."""
    # Strip due date suffix before normalizing
    text = DUE_DATE_RE.sub("", text)
    text = text.lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", text).strip()


def scan_daily_notes(daily_dir: Path) -> list[Task]:
    """Scan all daily note files for tasks."""
    if not daily_dir.exists():
        return []

    all_tasks: list[Task] = []
    for md_file in sorted(daily_dir.glob("*.md")):
        date_str = md_file.stem  # e.g. "2026-02-05"
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            continue
        tasks = _parse_tasks_from_file(md_file, date_str)
        all_tasks.extend(tasks)

    return all_tasks


def _parse_tasks_from_file(md_file: Path, date_str: str) -> list[Task]:
    """Parse tasks from a daily note's ## Tasks section."""
    lines = md_file.read_text(encoding="utf-8").split("\n")
    tasks: list[Task] = []
    in_tasks_section = False
    current_category = ""
    current_sub_project = ""

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect ## Tasks section start
        if stripped == "## Tasks":
            in_tasks_section = True
            continue

        # Detect end of Tasks section (another ## heading)
        if in_tasks_section and stripped.startswith("## ") and not stripped.startswith("### "):
            break

        if not in_tasks_section:
            continue

        # Track heading hierarchy
        if stripped.startswith("### ") and not stripped.startswith("#### "):
            current_category = stripped[4:].strip()
            current_sub_project = ""
            continue
        if stripped.startswith("#### "):
            current_sub_project = stripped[5:].strip()
            continue

        # Parse checkbox tasks
        checkbox_match = re.match(r"^-\s*\[([ xX])\]\s*(.+)$", stripped)
        if checkbox_match:
            completed = checkbox_match.group(1).lower() == "x"
            raw_text = checkbox_match.group(2).strip()

            # Extract due date if present
            due_date = ""
            due_match = DUE_DATE_RE.search(raw_text)
            if due_match:
                due_date = due_match.group(1)
                raw_text = DUE_DATE_RE.sub("", raw_text).strip()

            if raw_text:
                tasks.append(
                    Task(
                        text=raw_text,
                        completed=completed,
                        source_date=date_str,
                        category=current_category,
                        sub_project=current_sub_project,
                        line_number=i,
                        due_date=due_date,
                    )
                )

    return tasks


def aggregate_tasks(all_tasks: list[Task]) -> list[AggregatedTask]:
    """Group tasks by normalized text, maintaining category/sub-project from first appearance."""
    seen: dict[str, AggregatedTask] = {}

    for task in all_tasks:
        key = f"{task.category}|{task.sub_project}|{task.normalized}"
        if key not in seen:
            seen[key] = AggregatedTask(
                text=task.text,
                normalized=task.normalized,
                category=task.category,
                sub_project=task.sub_project,
                due_date=task.due_date,
            )
        seen[key].appearances.append(task)
        # Update due_date if a later appearance has one
        if task.due_date:
            seen[key].due_date = task.due_date

    return list(seen.values())


def _read_aggregate_completions(aggregate_file: Path) -> dict[str, bool]:
    """Read completion states from existing task files.

    Handles both table format (All Tasks) and list format (Completed Tasks).
    Returns dict of normalized_task_text -> completed.
    """
    if not aggregate_file.exists():
        return {}

    completions: dict[str, bool] = {}
    content = aggregate_file.read_text(encoding="utf-8")

    for line in content.split("\n"):
        stripped = line.strip()

        # Table format: | Status | Task | Added | Due | label |
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.split("|")]
            # cells[0] and cells[-1] are empty from leading/trailing |
            # cells[1]=Status, cells[2]=Task, cells[3]=Added, ...
            if len(cells) < 4:
                continue
            status_cell = cells[1]
            task_cell = cells[2]
            # Skip header/separator rows
            if task_cell.startswith("--") or task_cell == "Task" or status_cell == "Status":
                continue
            is_completed = status_cell.lower() == "done"
            # Clean task text: remove wiki-links and due date
            text = re.sub(r"\[\[\d{4}-\d{2}-\d{2}\]\]", "", task_cell).strip()
            text = DUE_DATE_RE.sub("", text).strip()
            normalized = _normalize(text)
            if normalized:
                completions[normalized] = is_completed
            continue

        # List format (Completed Tasks.md): - [x] task text [[date]] *(category)*
        checkbox_match = re.match(r"^-\s*\[([ xX])\]\s*(.+)$", stripped)
        if checkbox_match:
            completed = checkbox_match.group(1).lower() == "x"
            text = checkbox_match.group(2)
            # Remove trailing [[YYYY-MM-DD]], (day N), *(category)* markers
            text = re.sub(r"\s*\[\[\d{4}-\d{2}-\d{2}\]\].*$", "", text).strip()
            text = DUE_DATE_RE.sub("", text).strip()
            normalized = _normalize(text)
            if normalized:
                completions[normalized] = completed

    return completions


def _read_aggregate_due_dates(aggregate_file: Path) -> dict[str, str]:
    """Read due dates from the aggregate task table.

    Returns dict of normalized_task_text -> due_date_string (YYYY-MM-DD or "").
    """
    if not aggregate_file.exists():
        return {}

    due_dates: dict[str, str] = {}
    content = aggregate_file.read_text(encoding="utf-8")

    for line in content.split("\n"):
        stripped = line.strip()

        # Table format: | Status | Task | Added | Due | Timeline |
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.split("|")]
            # cells[0] and cells[-1] are empty from leading/trailing |
            if len(cells) < 6:
                continue
            status_cell = cells[1]
            task_cell = cells[2]
            due_cell = cells[4]
            # Skip header/separator rows
            if task_cell.startswith("--") or task_cell == "Task" or status_cell == "Status":
                continue
            # Clean task text: remove wiki-links
            text = re.sub(r"\[\[\d{4}-\d{2}-\d{2}\]\]", "", task_cell).strip()
            text = DUE_DATE_RE.sub("", text).strip()
            normalized = _normalize(text)
            if normalized:
                due_dates[normalized] = due_cell

    return due_dates


def _sync_changes_to_daily(
    daily_dir: Path,
    all_tasks: list[Task],
    existing_completions: dict[str, bool],
    existing_due_dates: dict[str, str] | None = None,
) -> int:
    """Push completions and due dates from aggregate file back to daily notes.

    If a task is marked completed in the aggregate but open in a daily note,
    update the daily note. If a due date was added/changed/removed in the
    aggregate, sync it back to the daily note.

    Returns number of daily note files updated.
    """
    if not existing_completions and not existing_due_dates:
        return 0

    if existing_due_dates is None:
        existing_due_dates = {}

    # Group tasks by source file
    tasks_by_file: dict[str, list[Task]] = {}
    for task in all_tasks:
        tasks_by_file.setdefault(task.source_date, []).append(task)

    updated_files = 0
    for date_str, tasks in tasks_by_file.items():
        daily_file = daily_dir / f"{date_str}.md"
        if not daily_file.exists():
            continue

        lines = daily_file.read_text(encoding="utf-8").split("\n")
        file_changed = False

        for task in tasks:
            old_line = lines[task.line_number]

            # Sync completions: aggregate completed -> daily note
            if not task.completed:
                agg_completed = existing_completions.get(task.normalized)
                if agg_completed:
                    new_line = old_line.replace("- [ ]", "- [x]", 1)
                    if old_line != new_line:
                        lines[task.line_number] = new_line
                        old_line = new_line
                        file_changed = True
                        logger.info("Synced completion: %s in %s", task.text, date_str)

            # Sync due dates: aggregate due date -> daily note
            # Only sync non-empty due dates from aggregate. If aggregate
            # has no date, don't clear the daily note's date (the daily
            # note is the source of truth for new dates).
            agg_due = existing_due_dates.get(task.normalized)
            if agg_due:  # only sync if aggregate has an actual date
                current_due = task.due_date
                if agg_due != current_due:
                    # Strip any existing due date from the line
                    new_line = DUE_DATE_RE.sub("", old_line).rstrip()
                    new_line = f"{new_line} (due: {agg_due})"
                    if old_line != new_line:
                        lines[task.line_number] = new_line
                        file_changed = True
                        logger.info(
                            "Synced due date: %s -> %s in %s",
                            task.text,
                            agg_due,
                            date_str,
                        )

        if file_changed:
            daily_file.write_text("\n".join(lines), encoding="utf-8")
            updated_files += 1

    return updated_files


def _write_aggregate_file(aggregate_file: Path, aggregated: list[AggregatedTask]) -> None:
    """Generate All Tasks.md as tables with only open tasks."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Group open tasks by category then sub_project
    by_category: dict[str, dict[str, list[AggregatedTask]]] = {}
    for task in aggregated:
        if task.completed:
            continue
        cat = task.category or "Uncategorized"
        sub = task.sub_project or ""
        by_category.setdefault(cat, {}).setdefault(sub, []).append(task)

    lines = [
        "---",
        "type: tasks",
        f"updated: {today}",
        "---",
        "",
        "# All Tasks",
        f"*Auto-generated by SecondBrain on {today}*",
        "",
    ]

    for cat in sorted(by_category.keys()):
        lines.append(f"## {cat}")
        lines.append("")

        subs = by_category[cat]
        for sub in sorted(subs.keys()):
            tasks = subs[sub]
            if sub:
                lines.append(f"### {sub}")
                lines.append("")

            # Sort: tasks with due dates first (earliest due), then by first appearance
            tasks.sort(key=lambda t: (t.due_date or "9999-99-99", t.first_date))

            # Table header
            lines.append("| Status | Task | Added | Due | Timeline |")
            lines.append("|:---:|------|:---:|:---:|:---:|")

            for task in tasks:
                status = "Open"
                added = f"[[{task.first_date}]]"
                due_col = task.due_date if task.due_date else ""
                label = task.due_label()

                lines.append(f"| {status} | {task.text} | {added} | {due_col} | {label} |")

            lines.append("")

    new_content = "\n".join(lines)
    if aggregate_file.exists() and aggregate_file.read_text(encoding="utf-8") == new_content:
        logger.info("Aggregate file unchanged: %s", aggregate_file)
        return
    aggregate_file.write_text(new_content, encoding="utf-8")
    logger.info("Wrote aggregate file: %s", aggregate_file)


def _write_completed_file(completed_file: Path, aggregated: list[AggregatedTask]) -> None:
    """Generate Completed Tasks.md with completed tasks ordered by completion date."""
    today = datetime.now().strftime("%Y-%m-%d")

    done_tasks = [t for t in aggregated if t.completed]
    done_tasks.sort(key=lambda t: t.latest_date, reverse=True)

    lines = [
        "---",
        "type: tasks",
        f"updated: {today}",
        "---",
        "",
        "# Completed Tasks",
        f"*Auto-generated by SecondBrain on {today}*",
        "",
    ]

    if not done_tasks:
        lines.append("*No completed tasks yet.*")
        lines.append("")
    else:
        # Group by completion date (most recent first)
        by_date: dict[str, list[AggregatedTask]] = {}
        for task in done_tasks:
            by_date.setdefault(task.latest_date, []).append(task)

        for date_str in sorted(by_date.keys(), reverse=True):
            lines.append(f"## {date_str}")
            lines.append("")
            for task in by_date[date_str]:
                cat_label = f" *({task.category}"
                if task.sub_project:
                    cat_label += f" > {task.sub_project}"
                cat_label += ")*"
                lines.append(f"- [x] {task.text} [[{task.first_date}]]{cat_label}")
            lines.append("")

    new_content = "\n".join(lines)
    if completed_file.exists() and completed_file.read_text(encoding="utf-8") == new_content:
        logger.info("Completed file unchanged: %s", completed_file)
        return
    completed_file.write_text(new_content, encoding="utf-8")
    logger.info("Wrote completed file: %s", completed_file)
