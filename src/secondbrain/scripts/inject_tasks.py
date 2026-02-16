"""Inject tasks into a daily note's ## Tasks section.

One-time / as-needed utility for retroactively adding tasks that were lost
due to the existing-note-append bug (tasks silently dropped when a capture
was routed to an existing note instead of a daily note).

Usage:
    uv run python -m secondbrain.scripts.inject_tasks --file tasks.json [--dry-run]
    uv run python -m secondbrain.scripts.inject_tasks --interactive [--dry-run]

JSON file format:
    {
      "date": "2026-02-15",
      "tasks": [
        {"text": "Do the thing", "category": "Personal", "sub_project": "Rachel", "due_date": "2026-03-31"},
        {"text": "Another task", "category": "Personal", "sub_project": "Family", "due_date": null}
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from secondbrain.config import get_settings
from secondbrain.scripts.inbox_processor import (
    VAULT_FOLDERS,
    _ensure_task_category,
    _ensure_task_hierarchy,
)


def inject_tasks(
    vault_path: Path,
    date_str: str,
    tasks: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> list[str]:
    """Inject tasks into a daily note, returning a list of action descriptions."""
    daily_dir = vault_path / VAULT_FOLDERS["daily"]
    daily_file = daily_dir / f"{date_str}.md"
    actions: list[str] = []

    if not daily_file.exists():
        actions.append(f"ERROR: Daily note not found: {daily_file}")
        return actions

    content = daily_file.read_text(encoding="utf-8")
    original = content

    for task in tasks:
        text = task.get("text", "").strip()
        if not text:
            continue

        # Skip if task text already in the file (dedup)
        if text in content:
            actions.append(f"SKIP (already exists): {text}")
            continue

        category = task.get("category")
        sub_project = task.get("sub_project")
        due_date = task.get("due_date")
        due_suffix = f" (due: {due_date})" if due_date else ""
        task_line = f"- [ ] {text}{due_suffix}"

        if category and sub_project:
            content = _ensure_task_hierarchy(content, category, sub_project, task_line)
        elif category:
            content = _ensure_task_category(content, category, task_line)
        else:
            # Fallback: append under ## Tasks with no category
            lines = content.split("\n")
            for i, ln in enumerate(lines):
                if ln.strip() == "## Tasks":
                    lines.insert(i + 1, task_line)
                    break
            content = "\n".join(lines)

        actions.append(
            f"INJECT: [{category or 'Uncategorized'}"
            f"{' > ' + sub_project if sub_project else ''}] {text}"
            f"{due_suffix}"
        )

    if content != original:
        if dry_run:
            actions.append(f"DRY RUN — would write to {daily_file}")
            print("\n--- Preview of modified file ---")
            print(content)
            print("--- End preview ---\n")
        else:
            daily_file.write_text(content, encoding="utf-8")
            actions.append(f"WRITTEN: {daily_file}")

    return actions


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject tasks into a daily note")
    parser.add_argument("--file", type=Path, help="JSON file with tasks to inject")
    parser.add_argument("--interactive", action="store_true", help="Enter tasks interactively")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    if not args.file and not args.interactive:
        parser.error("Provide --file or --interactive")

    settings = get_settings()
    if not settings.vault_path:
        print("ERROR: SECONDBRAIN_VAULT_PATH not configured")
        sys.exit(1)
    vault_path = settings.vault_path

    if args.file:
        data = json.loads(args.file.read_text(encoding="utf-8"))
        date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))
        tasks = data.get("tasks", [])
    else:
        date_str = input(f"Date [{datetime.now().strftime('%Y-%m-%d')}]: ").strip()
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        tasks = []
        print("Enter tasks (empty text to finish):")
        while True:
            text = input("  Task text: ").strip()
            if not text:
                break
            category = input("  Category [Personal]: ").strip() or "Personal"
            sub_project = input("  Sub-project []: ").strip() or None
            due_date = input("  Due date (YYYY-MM-DD) []: ").strip() or None
            tasks.append(
                {
                    "text": text,
                    "category": category,
                    "sub_project": sub_project,
                    "due_date": due_date,
                }
            )

    if not tasks:
        print("No tasks to inject.")
        sys.exit(0)

    print(f"\nInjecting {len(tasks)} task(s) into {date_str}...")
    actions = inject_tasks(vault_path, date_str, tasks, dry_run=args.dry_run)
    for action in actions:
        print(f"  {action}")
    print("Done.")


if __name__ == "__main__":
    main()
