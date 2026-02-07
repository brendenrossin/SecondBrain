"""Markdown-aware chunker for notes."""

import hashlib
import re

from secondbrain.models import Chunk, Note


class Chunker:
    """Markdown-aware chunker that preserves semantic boundaries."""

    # Recursive separators in order of preference
    SEPARATORS = [
        "\n# ",  # H1
        "\n## ",  # H2
        "\n### ",  # H3
        "\n#### ",  # H4
        "\n\n",  # Paragraphs
        "\n- ",  # Unordered lists
        "\n* ",  # Unordered lists (alt)
        "\n1. ",  # Ordered lists
        "\n",  # Line breaks
        ". ",  # Sentences
        "? ",
        "! ",
        "; ",
        ": ",
    ]

    def __init__(
        self,
        target_size: int = 700,
        overlap: int = 100,
        min_chunk_size: int = 100,
    ) -> None:
        """Initialize the chunker.

        Args:
            target_size: Target chunk size in characters.
            overlap: Overlap between chunks in characters.
            min_chunk_size: Minimum chunk size to keep.
        """
        self.target_size = target_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size

    def chunk_note(self, note: Note) -> list[Chunk]:
        """Chunk a note into smaller pieces.

        Args:
            note: The note to chunk.

        Returns:
            List of Chunk objects.
        """
        # Split content into sections by headings first
        sections = self._split_by_headings(note.content)

        chunks: list[Chunk] = []
        chunk_index = 0

        for heading_path, section_text in sections:
            # Further split large sections
            section_chunks = self._split_section(section_text)

            for text in section_chunks:
                if len(text.strip()) < self.min_chunk_size:
                    continue

                chunk_id = self._generate_chunk_id(note.path, heading_path, chunk_index, text)
                checksum = self._generate_checksum(text)

                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        note_path=note.path,
                        note_title=note.title,
                        heading_path=heading_path,
                        chunk_index=chunk_index,
                        chunk_text=text.strip(),
                        checksum=checksum,
                    )
                )
                chunk_index += 1

        return chunks

    def _split_by_headings(self, content: str) -> list[tuple[list[str], str]]:
        """Split content by headings, tracking the heading path.

        Returns:
            List of (heading_path, section_text) tuples.
        """
        # Pattern to match markdown headings
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

        sections: list[tuple[list[str], str]] = []
        current_path: list[str] = []
        current_levels: list[int] = []
        last_end = 0

        for match in heading_pattern.finditer(content):
            # Save content before this heading
            if last_end < match.start():
                text = content[last_end : match.start()].strip()
                if text:
                    sections.append((list(current_path), text))

            # Update heading path
            level = len(match.group(1))
            heading_text = match.group(2).strip()

            # Pop headings of same or deeper level
            while current_levels and current_levels[-1] >= level:
                current_levels.pop()
                current_path.pop()

            current_path.append(heading_text)
            current_levels.append(level)
            last_end = match.end()

        # Don't forget content after the last heading
        if last_end < len(content):
            text = content[last_end:].strip()
            if text:
                sections.append((list(current_path), text))

        # If no headings found, return the whole content
        if not sections and content.strip():
            sections = [([], content.strip())]

        return sections

    def _split_section(self, text: str) -> list[str]:
        """Split a section into smaller chunks if needed."""
        if len(text) <= self.target_size:
            return [text]

        return self._recursive_split(text, 0)

    def _recursive_split(self, text: str, sep_index: int) -> list[str]:
        """Recursively split text using separators."""
        if len(text) <= self.target_size:
            return [text]

        if sep_index >= len(self.SEPARATORS):
            # No more separators, force split
            return self._force_split(text)

        separator = self.SEPARATORS[sep_index]
        parts = text.split(separator)

        if len(parts) == 1:
            # Separator not found, try next one
            return self._recursive_split(text, sep_index + 1)

        # Merge small parts and split large ones
        result: list[str] = []
        current = ""

        for i, part in enumerate(parts):
            # Add separator back (except for first part)
            if i > 0:
                part = separator.lstrip("\n") + part

            if len(current) + len(part) <= self.target_size:
                current += part
            else:
                if current:
                    result.append(current)
                if len(part) > self.target_size:
                    # Recursively split large part
                    result.extend(self._recursive_split(part, sep_index + 1))
                    current = ""
                else:
                    current = part

        if current:
            result.append(current)

        return result

    def _force_split(self, text: str) -> list[str]:
        """Force split text at target size with overlap."""
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.target_size

            # Try to find a word boundary
            if end < len(text):
                space_idx = text.rfind(" ", start, end)
                if space_idx > start:
                    end = space_idx

            chunks.append(text[start:end].strip())
            start = end - self.overlap

        return chunks

    def _generate_chunk_id(
        self, note_path: str, heading_path: list[str], chunk_index: int, text: str
    ) -> str:
        """Generate a stable chunk ID."""
        normalized_text = self._normalize_text(text)
        data = f"{note_path}|{'|'.join(heading_path)}|{chunk_index}|{normalized_text}"
        return hashlib.sha1(data.encode()).hexdigest()[:16]

    def _generate_checksum(self, text: str) -> str:
        """Generate a checksum for change detection."""
        normalized = self._normalize_text(text)
        return hashlib.sha1(normalized.encode()).hexdigest()[:16]

    def _normalize_text(self, text: str) -> str:
        """Normalize text for hashing."""
        # Collapse whitespace
        return " ".join(text.split())
