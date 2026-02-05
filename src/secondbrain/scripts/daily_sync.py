"""CLI entry point for daily vault sync operations."""

import argparse
import logging
import sys
from pathlib import Path

from secondbrain.config import get_settings
from secondbrain.scripts.inbox_processor import process_inbox
from secondbrain.scripts.task_aggregator import sync_tasks


def main() -> None:
    parser = argparse.ArgumentParser(description="SecondBrain daily vault sync")
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["inbox", "tasks", "all"],
        help="Which sync to run (default: all)",
    )
    parser.add_argument(
        "--vault-path",
        type=Path,
        default=None,
        help="Override vault path (default: from config/env)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("secondbrain.scripts")

    vault_path = args.vault_path
    if vault_path is None:
        settings = get_settings()
        vault_path = settings.vault_path

    if vault_path is None:
        logger.error("No vault path configured. Set SECONDBRAIN_VAULT_PATH or use --vault-path")
        sys.exit(1)

    vault_path = Path(vault_path)
    if not vault_path.exists():
        logger.error("Vault path does not exist: %s", vault_path)
        sys.exit(1)

    logger.info("Vault path: %s", vault_path)

    if args.command in ("inbox", "all"):
        logger.info("--- Processing inbox ---")
        actions = process_inbox(vault_path)
        if actions:
            for action in actions:
                logger.info("  %s", action)
        else:
            logger.info("  No inbox items to process")

    if args.command in ("tasks", "all"):
        logger.info("--- Syncing tasks ---")
        summary = sync_tasks(vault_path)
        logger.info("  %s", summary)

    logger.info("Done!")


if __name__ == "__main__":
    main()
