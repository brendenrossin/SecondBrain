"""CLI entry point for daily vault sync operations."""

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from secondbrain.config import get_settings
from secondbrain.scripts.inbox_processor import process_inbox
from secondbrain.scripts.project_sync import sync_projects
from secondbrain.scripts.task_aggregator import sync_tasks

logger = logging.getLogger("secondbrain.scripts")


def _log_structured(event: str, **kwargs: Any) -> None:
    """Log a structured JSON event for critical sync milestones."""
    logger.info(json.dumps({"event": event, **kwargs}))


def _rotate_logs(data_path: Path, max_size_mb: float = 10.0) -> None:
    """Rotate log files that exceed max_size_mb."""
    for log_name in ["daily-sync.log", "api.log", "ui.log", "queries.jsonl"]:
        log_file = data_path / log_name
        if log_file.exists() and log_file.stat().st_size > max_size_mb * 1024 * 1024:
            rotated = data_path / f"{log_name}.old"
            if rotated.exists():
                rotated.unlink()
            log_file.rename(rotated)
            logger.info("Rotated %s (exceeded %.1f MB)", log_name, max_size_mb)


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

    # Try to tell the running server to reindex immediately
    try:
        req = urllib.request.Request(
            f"http://{settings.host}:{settings.port}/api/v1/index",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=b"{}",
        )
        urllib.request.urlopen(req, timeout=120)
        return "Reindex triggered via API (server reindexed immediately)"
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        logger.info("API reindex trigger failed (%s), using file trigger", e)
        return "Reindex trigger written (server not reachable; will reindex on next query)"


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
        choices=["inbox", "tasks", "projects", "index", "extract", "weekly", "all"],
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

    settings = get_settings()

    # Rotate logs before doing anything else
    data_path = Path(settings.data_path)
    data_path.mkdir(parents=True, exist_ok=True)
    _rotate_logs(data_path)

    vault_path = args.vault_path
    if vault_path is None:
        vault_path = settings.vault_path

    if vault_path is None:
        logger.error("No vault path configured. Set SECONDBRAIN_VAULT_PATH or use --vault-path")
        sys.exit(1)

    vault_path = Path(vault_path)
    if not vault_path.exists():
        logger.error("Vault path does not exist: %s", vault_path)
        sys.exit(1)

    logger.info("Vault path: %s", vault_path)
    sync_start = time.time()

    try:
        if args.command in ("inbox", "all"):
            logger.info("--- Processing inbox ---")
            step_start = time.time()
            actions = process_inbox(vault_path)
            elapsed = int((time.time() - step_start) * 1000)
            count = len(actions) if actions else 0
            if actions:
                for action in actions:
                    logger.info("  %s", action)
            else:
                logger.info("  No inbox items to process")
            _log_structured("inbox_complete", processed=count, duration_ms=elapsed)

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
            step_start = time.time()
            summary = reindex_vault(vault_path)
            elapsed = int((time.time() - step_start) * 1000)
            logger.info("  %s", summary)
            _log_structured("reindex_complete", summary=summary, duration_ms=elapsed)

        if args.command in ("extract", "all"):
            logger.info("--- Extracting metadata ---")
            step_start = time.time()
            summary = extract_metadata(vault_path)
            elapsed = int((time.time() - step_start) * 1000)
            logger.info("  %s", summary)
            _log_structured("extraction_complete", summary=summary, duration_ms=elapsed)

        if args.command == "weekly":
            logger.info("--- Generating weekly review ---")
            from secondbrain.scripts.weekly_review import generate_weekly_review

            summary = generate_weekly_review(vault_path)
            logger.info("  %s", summary)

        # Write sync completion marker
        total_elapsed = int((time.time() - sync_start) * 1000)
        marker = data_path / ".sync_completed"
        marker.write_text(datetime.now().isoformat())
        logger.info("Sync completed successfully in %dms", total_elapsed)
        _log_structured("sync_complete", command=args.command, duration_ms=total_elapsed)

    except Exception as e:
        # Write sync failure marker
        marker = data_path / ".sync_failed"
        marker.write_text(f"{datetime.now().isoformat()}: {e!s}")
        logger.error("Sync FAILED: %s", e)
        _log_structured("sync_failed", error=str(e))
        raise


if __name__ == "__main__":
    main()
