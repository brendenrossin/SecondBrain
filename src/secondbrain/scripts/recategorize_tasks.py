"""One-time script to recategorize existing Personal tasks into subcategories.

Moves 16 flat Personal tasks (and one category change) into their correct
subcategories using update_task_in_daily() from the task aggregator.

Usage:
    python -m secondbrain.scripts.recategorize_tasks [--dry-run]
"""

from __future__ import annotations

import argparse
import logging

from secondbrain.config import get_settings
from secondbrain.scripts.task_aggregator import (
    aggregate_tasks,
    scan_daily_notes,
    sync_tasks,
    update_task_in_daily,
)

logger = logging.getLogger(__name__)

# (task_text_substring, current_category, current_sub_project, new_category, new_sub_project)
RECATEGORIZATIONS = [
    # Gifts
    ("Confer with Rachel on which wines Chad should get", "Personal", "", "Personal", "Gifts"),
    ("Follow up with Chad on wine selection", "Personal", "", "Personal", "Gifts"),
    ("Get Evan (sister) a birthday/christmas gift", "Personal", "", "Personal", "Gifts"),
    # Chores
    ("Take out the trash", "Personal", "", "Personal", "Chores"),
    ("Throw out the rat trap", "Personal", "", "Personal", "Chores"),
    ("Finish laundry", "Personal", "", "Personal", "Chores"),
    # Errands
    ("Get propane tanks", "Personal", "", "Personal", "Errands"),
    ("Call Gone Bananas Bread", "Personal", "", "Personal", "Errands"),
    # Health
    ("Look into getting a dermatologist appointment", "Personal", "", "Personal", "Health"),
    # Projects
    ("Complete Azure AI engineering AZ-102 Udemy course", "Personal", "", "Personal", "Projects"),
    ("Finish Langchain course on Coursera", "Personal", "", "Personal", "Projects"),
    (
        "Start next Coursera course after Azure certification",
        "Personal",
        "",
        "Personal",
        "Projects",
    ),
    # General
    ("Obtain W2 from Genmark", "Personal", "", "Personal", "General"),
    ("Finish taxes, including all investment accounts", "Personal", "", "Personal", "General"),
    ("Follow up on David", "Personal", "", "Personal", "General"),
    # PwC (category change)
    ("Go over Azure AI-102 learning path and take practice tests", "Personal", "", "PwC", "Admin"),
]


def run(dry_run: bool = False) -> None:
    """Execute the recategorization."""
    settings = get_settings()
    if not settings.vault_path:
        logger.error("SECONDBRAIN_VAULT_PATH not configured")
        return
    vault_path = settings.vault_path
    daily_dir = vault_path / "00_Daily"

    # Scan current tasks to find matches
    all_tasks = scan_daily_notes(daily_dir)
    aggregated = aggregate_tasks(all_tasks)

    moved = 0
    skipped = 0

    for substring, _, _, new_cat, new_sub in RECATEGORIZATIONS:
        # Find matching task by substring
        matched_text = None
        matched_cat = None
        matched_sub = None
        for agg in aggregated:
            if substring.lower() in agg.text.lower():
                matched_text = agg.text
                matched_cat = agg.category
                matched_sub = agg.sub_project
                break

        if not matched_text:
            logger.warning("Task not found: '%s'", substring)
            skipped += 1
            continue

        # Skip if already in the correct category/sub_project
        if matched_cat == new_cat and matched_sub == new_sub:
            logger.info("Already correct: '%s' -> %s / %s", matched_text, new_cat, new_sub)
            skipped += 1
            continue

        if dry_run:
            logger.info(
                "[DRY RUN] Would move: '%s' from %s/%s -> %s/%s",
                matched_text,
                matched_cat,
                matched_sub or "(none)",
                new_cat,
                new_sub,
            )
            moved += 1
            continue

        result = update_task_in_daily(
            vault_path,
            matched_text,
            category=matched_cat or "",
            sub_project=matched_sub or "",
            new_category=new_cat,
            new_sub_project=new_sub,
        )
        if result:
            logger.info("Moved: '%s' -> %s / %s", matched_text, new_cat, new_sub)
            moved += 1
        else:
            logger.warning("Failed to move: '%s'", matched_text)
            skipped += 1

    # Regenerate aggregate files
    if not dry_run and moved > 0:
        summary = sync_tasks(vault_path)
        logger.info("Sync complete: %s", summary)

    action = "Would move" if dry_run else "Moved"
    logger.info("Done: %s %d tasks, skipped %d", action, moved, skipped)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Recategorize existing Personal tasks")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would change without writing"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
