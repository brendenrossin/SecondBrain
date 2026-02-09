"""Vault connector for reading Obsidian vault files."""

import fnmatch
import hashlib
import logging
from pathlib import Path

from secondbrain.models import Note
from secondbrain.vault.parser import parse_markdown

logger = logging.getLogger(__name__)


class VaultConnector:
    """Connects to an Obsidian vault and reads notes."""

    DEFAULT_EXCLUDES = [
        ".obsidian/*",
        ".trash/*",
        "node_modules/*",
        ".git/*",
        "*.excalidraw.md",
        "Inbox/*",
        "Tasks/All Tasks.md",
        "Tasks/Completed Tasks.md",
        "90_Meta/Templates/*",
    ]

    def __init__(
        self,
        vault_path: Path,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ) -> None:
        """Initialize the vault connector.

        Args:
            vault_path: Path to the Obsidian vault root.
            include_patterns: Glob patterns for files to include. Defaults to ["**/*.md"].
            exclude_patterns: Glob patterns for files to exclude.
        """
        self.vault_path = vault_path
        self.include_patterns = include_patterns or ["**/*.md"]
        self.exclude_patterns = exclude_patterns or self.DEFAULT_EXCLUDES

    def _should_exclude(self, relative_path: str) -> bool:
        """Check if a file should be excluded based on patterns."""
        return any(fnmatch.fnmatch(relative_path, pattern) for pattern in self.exclude_patterns)

    def list_notes(self) -> list[Path]:
        """List all note files in the vault.

        Returns:
            List of paths to note files, relative to vault root.
        """
        notes: list[Path] = []
        for pattern in self.include_patterns:
            for file_path in self.vault_path.glob(pattern):
                if file_path.is_file():
                    relative = file_path.relative_to(self.vault_path)
                    if not self._should_exclude(str(relative)):
                        notes.append(relative)
        return sorted(set(notes))

    def read_note(self, relative_path: Path) -> Note:
        """Read and parse a single note.

        Args:
            relative_path: Path to the note, relative to vault root.

        Returns:
            Parsed Note object.
        """
        full_path = self.vault_path / relative_path
        content = full_path.read_text(encoding="utf-8")
        return parse_markdown(str(relative_path), content)

    def get_file_metadata(self) -> dict[str, tuple[float, str]]:
        """Get metadata for all vault files.

        Returns:
            Dict of {relative_path: (mtime, sha1_hash)} for all vault .md files.
        """
        metadata: dict[str, tuple[float, str]] = {}
        for path in self.list_notes():
            full_path = self.vault_path / path
            try:
                mtime = full_path.stat().st_mtime
                content = full_path.read_bytes()
                content_hash = hashlib.sha1(content).hexdigest()
                metadata[str(path)] = (mtime, content_hash)
            except OSError:
                continue
        return metadata

    def read_all_notes(self) -> list[Note]:
        """Read all notes in the vault.

        Returns:
            List of parsed Note objects.
        """
        notes = []
        for path in self.list_notes():
            try:
                notes.append(self.read_note(path))
            except Exception as e:
                # Log error but continue with other notes
                logger.warning("Error reading %s: %s", path, e)
        return notes
