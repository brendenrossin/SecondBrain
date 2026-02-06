"""CLI entry point for daily vault sync operations."""

import argparse
import logging
import sys
from pathlib import Path

from secondbrain.config import get_settings
from secondbrain.scripts.inbox_processor import process_inbox
from secondbrain.scripts.task_aggregator import sync_tasks

logger = logging.getLogger("secondbrain.scripts")


def reindex_vault(vault_path: Path, data_path: Path | None = None) -> str:
    """Re-index the vault into vector + lexical stores.

    Returns a summary string.
    """
    from secondbrain.indexing.chunker import Chunker
    from secondbrain.indexing.embedder import Embedder
    from secondbrain.stores.lexical import LexicalStore
    from secondbrain.stores.vector import VectorStore
    from secondbrain.vault.connector import VaultConnector

    settings = get_settings()
    if data_path is None:
        data_path = Path(settings.data_path) if settings.data_path else Path("data")
    data_path.mkdir(parents=True, exist_ok=True)

    connector = VaultConnector(vault_path)
    chunker = Chunker()
    embedder = Embedder(model_name=settings.embedding_model)
    vector_store = VectorStore(data_path / "chroma")
    lexical_store = LexicalStore(data_path / "lexical.db")

    notes = connector.read_all_notes()
    if not notes:
        return "Reindex: 0 notes, 0 chunks"

    all_chunks = []
    for note in notes:
        all_chunks.extend(chunker.chunk_note(note))

    if all_chunks:
        texts = [c.chunk_text for c in all_chunks]
        embeddings = embedder.embed(texts)
        vector_store.add_chunks(all_chunks, embeddings)
        lexical_store.add_chunks(all_chunks)

    return f"Reindex: {len(notes)} notes, {len(all_chunks)} chunks"


def main() -> None:
    parser = argparse.ArgumentParser(description="SecondBrain daily vault sync")
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["inbox", "tasks", "index", "all"],
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

    if args.command in ("index", "all"):
        logger.info("--- Reindexing vault ---")
        summary = reindex_vault(vault_path)
        logger.info("  %s", summary)

    logger.info("Done!")


if __name__ == "__main__":
    main()
