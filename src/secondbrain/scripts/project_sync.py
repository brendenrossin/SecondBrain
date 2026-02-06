"""Project sync: updates project files with open tasks and recent notes."""

import logging
import re
import string
from datetime import datetime, timedelta
from pathlib import Path

from secondbrain.scripts.task_aggregator import (
    AggregatedTask,
    aggregate_tasks,
    scan_daily_notes,
)

logger = logging.getLogger(__name__)

AUTO_START = "<!-- AUTO-GENERATED: Do not edit below this line -->"
AUTO_END = "<!-- END AUTO-GENERATED -->"


def normalize_project_name(name: str) -> str:
    """Normalize a project name for fuzzy matching.

    Strips file extension, lowercases, removes punctuation and whitespace.
    """
    # Remove .md extension
    if name.endswith(".md"):
        name = name[:-3]
    name = name.lower().strip()
    name = name.translate(str.maketrans("", "", string.punctuation))
    # Remove all whitespace for matching (so "SecondBrain" matches "Second Brain")
    return re.sub(r"\s+", "", name).strip()


def match_project(project_name: str, sub_project: str) -> bool:
    """Check if a sub_project name matches a project file name.

    Uses substring matching after normalization.
    """
    if not sub_project:
        return False
    norm_project = normalize_project_name(project_name)
    norm_sub = normalize_project_name(sub_project)
    if not norm_project or not norm_sub:
        return False
    return norm_project in norm_sub or norm_sub in norm_project


def _extract_daily_notes_mentions(
    daily_dir: Path, project_name: str, days: int = 30,
) -> list[tuple[str, str]]:
    """Extract notes from daily files that mention the project.

    Scans ## Notes sections in recent daily notes for lines mentioning
    the project name. Returns list of (date, note_line) tuples.
    """
    if not daily_dir.exists():
        return []

    norm_project = normalize_project_name(project_name)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    mentions: list[tuple[str, str]] = []

    for md_file in sorted(daily_dir.glob("*.md"), reverse=True):
        date_str = md_file.stem
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            continue
        if date_str < cutoff:
            break

        lines = md_file.read_text(encoding="utf-8").split("\n")
        in_notes_section = False

        for line in lines:
            stripped = line.strip()
            if stripped == "## Notes":
                in_notes_section = True
                continue
            if in_notes_section and stripped.startswith("## "):
                break
            if not in_notes_section:
                continue

            # Check if this line mentions the project (bullet lines only)
            if norm_project and norm_project in line.lower() and stripped.startswith("- "):
                mentions.append((date_str, stripped))

    return mentions


def _build_task_table(tasks: list[AggregatedTask]) -> list[str]:
    """Build a markdown table for tasks (same format as All Tasks.md)."""
    if not tasks:
        return ["*No matching open tasks.*", ""]

    lines = [
        "| Status | Task | Added | Due | Timeline |",
        "|:---:|------|:---:|:---:|:---:|",
    ]
    tasks.sort(key=lambda t: (t.due_date or "9999-99-99", t.first_date))
    for task in tasks:
        status = "Open"
        added = f"[[{task.first_date}]]"
        due_col = task.due_date if task.due_date else ""
        label = task.due_label()
        lines.append(f"| {status} | {task.text} | {added} | {due_col} | {label} |")
    lines.append("")
    return lines


def _build_notes_section(mentions: list[tuple[str, str]]) -> list[str]:
    """Build a bullet list of recent notes mentioning the project."""
    if not mentions:
        return ["*No recent notes mentioning this project.*", ""]

    lines = []
    current_date = ""
    for date_str, note_line in mentions:
        if date_str != current_date:
            if current_date:
                lines.append("")
            lines.append(f"**[[{date_str}]]**")
            current_date = date_str
        lines.append(note_line)
    lines.append("")
    return lines


def _update_auto_section(content: str, section_heading: str, new_body: list[str]) -> str:
    """Update or insert an auto-generated section in a markdown file.

    Preserves content outside the AUTO-GENERATED markers. If the section
    doesn't exist, appends it.
    """
    section_re = re.compile(
        rf"(^{re.escape(section_heading)}\s*\n)"
        rf"({re.escape(AUTO_START)}\n)"
        rf"(.*?)"
        rf"({re.escape(AUTO_END)})",
        re.MULTILINE | re.DOTALL,
    )

    replacement_body = "\n".join(new_body)
    replacement = f"{section_heading}\n{AUTO_START}\n{replacement_body}\n{AUTO_END}"

    match = section_re.search(content)
    if match:
        return content[:match.start()] + replacement + content[match.end():]

    # Section doesn't exist: append
    if not content.endswith("\n"):
        content += "\n"
    content += f"\n{replacement}\n"
    return content


def sync_projects(
    vault_path: Path,
    aggregated_tasks: list[AggregatedTask] | None = None,
) -> str:
    """Sync project files with open tasks and recent notes.

    Args:
        vault_path: Path to the vault root.
        aggregated_tasks: Pre-aggregated tasks (if None, scans daily notes).

    Returns:
        Summary of actions taken.
    """
    projects_dir = vault_path / "20_Projects"
    daily_dir = vault_path / "00_Daily"

    if not projects_dir.exists():
        return "No 20_Projects directory found"

    # Get aggregated tasks if not provided
    if aggregated_tasks is None:
        all_tasks = scan_daily_notes(daily_dir)
        aggregated_tasks = aggregate_tasks(all_tasks)

    # Get open tasks only
    open_tasks = [t for t in aggregated_tasks if not t.completed]

    project_files = sorted(projects_dir.glob("*.md"))
    updated = 0

    for project_file in project_files:
        project_name = project_file.stem

        # Match tasks to this project
        matching_tasks = [
            t for t in open_tasks
            if match_project(project_name, t.sub_project)
        ]

        # Extract note mentions from daily notes
        mentions = _extract_daily_notes_mentions(daily_dir, project_name)

        # Skip if nothing to show
        if not matching_tasks and not mentions:
            continue

        content = project_file.read_text(encoding="utf-8")
        original = content

        # Update Open Tasks section
        task_lines = _build_task_table(matching_tasks)
        content = _update_auto_section(content, "## Open Tasks", task_lines)

        # Update Recent Notes section
        notes_lines = _build_notes_section(mentions)
        content = _update_auto_section(content, "## Recent Notes", notes_lines)

        if content != original:
            project_file.write_text(content, encoding="utf-8")
            updated += 1
            logger.info("Updated project file: %s", project_file.name)

    return f"Project sync: {updated} project files updated"
