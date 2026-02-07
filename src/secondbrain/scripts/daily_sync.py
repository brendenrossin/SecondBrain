"""CLI entry point for daily vault sync operations."""

import argparse
import logging
import sys
from pathlib import Path

from secondbrain.config import get_settings
from secondbrain.scripts.inbox_processor import process_inbox
from secondbrain.scripts.project_sync import sync_projects
from secondbrain.scripts.task_aggregator import sync_tasks

logger = logging.getLogger("secondbrain.scripts")


def reindex_vault(vault_path: Path, data_path: Path | None = None) -> str:
    """Signal the UI server to re-index by writing a trigger file.

    The UI process is the sole owner of the stores (ChromaDB + SQLite).
    Running reindex from a separate process causes corruption, so daily sync
    only writes a trigger that the UI picks up on the next query.

    Returns a summary string.
    """
    settings = get_settings()
    if data_path is None:
        data_path = Path(settings.data_path) if settings.data_path else Path("data")
    data_path.mkdir(parents=True, exist_ok=True)

    trigger = data_path / ".reindex_needed"
    trigger.write_text(str(vault_path))
    return "Reindex trigger written (UI will reindex on next query)"


def extract_metadata(vault_path: Path, data_path: Path | None = None) -> str:
    """Run metadata extraction for new/modified notes.

    Unlike reindexing, extraction runs in-process (not via trigger file)
    because it only touches the metadata SQLite DB, not ChromaDB.
    """
    settings = get_settings()
    if data_path is None:
        data_path = Path(settings.data_path) if settings.data_path else Path("data")

    from secondbrain.extraction.extractor import MetadataExtractor
    from secondbrain.scripts.llm_client import LLMClient
    from secondbrain.stores.metadata import MetadataStore
    from secondbrain.vault.connector import VaultConnector

    connector = VaultConnector(vault_path)
    metadata_store = MetadataStore(data_path / settings.metadata_db_name)
    extractor = MetadataExtractor(LLMClient())

    vault_files = connector.get_file_metadata()
    current_hashes = {path: h for path, (_mtime, h) in vault_files.items()}
    stale_paths = metadata_store.get_stale(current_hashes)

    if not stale_paths:
        metadata_store.close()
        return "All notes up to date"

    extracted = 0
    failed = 0
    for path in stale_paths:
        try:
            note = connector.read_note(Path(path))
            metadata = extractor.extract(note)
            metadata_store.upsert(metadata)
            extracted += 1
        except Exception:
            logger.warning("Failed to extract %s", path, exc_info=True)
            failed += 1

    metadata_store.close()
    return (
        f"Extracted {extracted}, failed {failed}, skipped {len(vault_files) - extracted - failed}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="SecondBrain daily vault sync")
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["inbox", "tasks", "projects", "index", "extract", "all"],
        help="Which sync to run (default: all)",
    )
    parser.add_argument(
        "--vault-path",
        type=Path,
        default=None,
        help="Override vault path (default: from config/env)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

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

    if args.command in ("projects", "all"):
        logger.info("--- Syncing projects ---")
        summary = sync_projects(vault_path)
        logger.info("  %s", summary)

    if args.command in ("index", "all"):
        logger.info("--- Reindexing vault ---")
        summary = reindex_vault(vault_path)
        logger.info("  %s", summary)

    if args.command in ("extract", "all"):
        logger.info("--- Extracting metadata ---")
        summary = extract_metadata(vault_path)
        logger.info("  %s", summary)

    logger.info("Done!")


if __name__ == "__main__":
    main()
