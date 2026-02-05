"""Task aggregator: scans daily notes for tasks, builds aggregated view with bi-dir sync."""

import logging
import re
import string
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """A single task extracted from a daily note."""

    text: str
    completed: bool
    source_date: str  # YYYY-MM-DD
    category: str  # e.g. "AT&T", "PwC", "Personal"
    sub_project: str  # e.g. "AI Receptionist", "" for none
    line_number: int  # line index in source file
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
    appearances: list[Task] = field(default_factory=list)

    @property
    def completed(self) -> bool:
        """Task is completed if its most recent appearance is completed."""
        if not self.appearances:
            return False
        # Most recent appearance determines completion status
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


def sync_tasks(vault_path: Path) -> str:
    """Run the full task aggregation and bi-directional sync.

    Returns a summary of actions taken.
    """
    daily_dir = vault_path / "00_Daily"
    tasks_dir = vault_path / "Tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    aggregate_file = tasks_dir / "All Tasks.md"

    # Step 1: Read existing aggregate completion states (for bi-dir sync)
    existing_completions = _read_aggregate_completions(aggregate_file)

    # Step 2: Scan daily notes for all tasks
    all_tasks = _scan_daily_notes(daily_dir)

    # Step 3: Bi-directional sync — push completions from aggregate back to daily notes
    updates = _sync_completions_to_daily(daily_dir, all_tasks, existing_completions)

    # Step 4: Re-scan daily notes after sync (picks up any changes)
    if updates > 0:
        all_tasks = _scan_daily_notes(daily_dir)

    # Step 5: Aggregate tasks by normalized text
    aggregated = _aggregate_tasks(all_tasks)

    # Step 6: Generate the aggregate file
    _write_aggregate_file(aggregate_file, aggregated)

    open_count = sum(1 for t in aggregated if not t.completed)
    done_count = sum(1 for t in aggregated if t.completed)
    return (
        f"Synced tasks: {open_count} open, {done_count} completed, "
        f"{updates} daily notes updated"
    )


def _normalize(text: str) -> str:
    """Normalize task text for matching: lowercase, strip punctuation and whitespace."""
    text = text.lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", text).strip()


def _scan_daily_notes(daily_dir: Path) -> list[Task]:
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
            text = checkbox_match.group(2).strip()
            if text:
                tasks.append(Task(
                    text=text,
                    completed=completed,
                    source_date=date_str,
                    category=current_category,
                    sub_project=current_sub_project,
                    line_number=i,
                ))

    return tasks


def _aggregate_tasks(all_tasks: list[Task]) -> list[AggregatedTask]:
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
            )
        seen[key].appearances.append(task)

    return list(seen.values())


def _read_aggregate_completions(aggregate_file: Path) -> dict[str, bool]:
    """Read completion states from existing All Tasks.md.

    Returns dict of normalized_task_text -> completed.
    """
    if not aggregate_file.exists():
        return {}

    completions: dict[str, bool] = {}
    content = aggregate_file.read_text(encoding="utf-8")

    for line in content.split("\n"):
        stripped = line.strip()
        checkbox_match = re.match(r"^-\s*\[([ xX])\]\s*(.+)$", stripped)
        if checkbox_match:
            completed = checkbox_match.group(1).lower() == "x"
            # Extract task text (remove the [[date]] wiki-link and day count)
            text = checkbox_match.group(2)
            # Remove trailing [[YYYY-MM-DD]] and (day N) markers
            text = re.sub(r"\s*\[\[\d{4}-\d{2}-\d{2}\]\].*$", "", text).strip()
            normalized = _normalize(text)
            if normalized:
                completions[normalized] = completed

    return completions


def _sync_completions_to_daily(
    daily_dir: Path,
    all_tasks: list[Task],
    existing_completions: dict[str, bool],
) -> int:
    """Push completions from aggregate file back to daily notes.

    If a task is marked completed in the aggregate but open in a daily note,
    update the daily note.

    Returns number of daily note files updated.
    """
    if not existing_completions:
        return 0

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
            if task.completed:
                continue  # Already completed in daily, nothing to sync

            # Check if aggregate has it as completed
            agg_completed = existing_completions.get(task.normalized)
            if agg_completed:
                # Update the daily note line
                old_line = lines[task.line_number]
                new_line = old_line.replace("- [ ]", "- [x]", 1)
                if old_line != new_line:
                    lines[task.line_number] = new_line
                    file_changed = True
                    logger.info(
                        "Synced completion: %s in %s", task.text, date_str
                    )

        if file_changed:
            daily_file.write_text("\n".join(lines), encoding="utf-8")
            updated_files += 1

    return updated_files


def _write_aggregate_file(aggregate_file: Path, aggregated: list[AggregatedTask]) -> None:
    """Generate the All Tasks.md file."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Group by category then sub_project
    by_category: dict[str, dict[str, list[AggregatedTask]]] = {}
    for task in aggregated:
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

            # Sort: open tasks first (oldest first), then completed
            open_tasks = [t for t in tasks if not t.completed]
            done_tasks = [t for t in tasks if t.completed]

            open_tasks.sort(key=lambda t: t.first_date)
            done_tasks.sort(key=lambda t: t.latest_date, reverse=True)

            for task in open_tasks:
                days = task.days_open
                day_str = f" *(day {days})*" if days > 0 else ""
                lines.append(
                    f"- [ ] {task.text} [[{task.first_date}]]{day_str}"
                )

            if done_tasks:
                if open_tasks:
                    lines.append("")
                for task in done_tasks:
                    lines.append(
                        f"- [x] {task.text} [[{task.latest_date}]]"
                    )

            lines.append("")

    aggregate_file.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote aggregate file: %s", aggregate_file)
