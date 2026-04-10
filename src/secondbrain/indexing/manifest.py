"""Vault manifest generator for RAG-3: topic-level overview injected into answerer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from secondbrain.stores.lexical import LexicalStore


class ManifestGenerator:
    """Generates a compact text summary of vault contents from the lexical store."""

    def generate(self, lexical_store: LexicalStore) -> str:
        """Build a vault-level manifest grouped by folder.

        Queries distinct (note_folder, note_title) pairs from the chunks table
        and produces a compact summary (~200-500 tokens) suitable for injection
        into the LLM system prompt.

        Returns empty string if the store has no chunks.
        """
        rows = lexical_store.conn.execute(
            "SELECT DISTINCT note_folder, note_title FROM chunks ORDER BY note_folder, note_title"
        ).fetchall()

        if not rows:
            return ""

        folders: dict[str, list[str]] = {}
        for row in rows:
            folder = row[0] or "Uncategorized"
            title = row[1]
            folders.setdefault(folder, []).append(title)

        lines = ["VAULT CONTENTS OVERVIEW:"]
        for folder, titles in sorted(folders.items()):
            titles_str = ", ".join(titles)
            lines.append(f"  [{folder}]: {titles_str}")

        return "\n".join(lines)
