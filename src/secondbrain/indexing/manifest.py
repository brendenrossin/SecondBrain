"""Vault manifest generator for topic-aware answering."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from secondbrain.stores.lexical import LexicalStore


class ManifestGenerator:
    """Generates a compact vault manifest from indexed content."""

    def generate(self, lexical_store: LexicalStore) -> str:
        """Generate a vault manifest summarizing what topics the knowledge base covers.

        Queries all distinct notes and their heading paths from the lexical store,
        groups by folder, and produces a compact text summary.
        """
        cursor = lexical_store.conn.execute("""
            SELECT DISTINCT note_folder, note_title, heading_path
            FROM chunks
            ORDER BY note_folder, note_title
        """)
        rows = cursor.fetchall()

        if not rows:
            return ""

        folders: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for row in rows:
            folder = row["note_folder"] or "Uncategorized"
            heading = row["heading_path"]
            if heading:
                top_heading = heading.split("|")[0]
                if top_heading:
                    folders[folder][row["note_title"]].add(top_heading)
            else:
                folders[folder][row["note_title"]]  # ensure title entry exists

        lines = ["VAULT CONTENTS OVERVIEW:"]
        for folder, notes in sorted(folders.items()):
            note_summaries = []
            for title, headings in sorted(notes.items()):
                if headings:
                    note_summaries.append(f"{title} ({', '.join(sorted(headings))})")
                else:
                    note_summaries.append(title)
            lines.append(f"- {folder}: {'; '.join(note_summaries)}")

        return "\n".join(lines)
