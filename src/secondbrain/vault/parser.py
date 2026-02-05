"""Markdown parser for Obsidian notes."""

from pathlib import Path

import frontmatter

from secondbrain.models import Note


def parse_markdown(path: str, content: str) -> Note:
    """Parse a markdown file with frontmatter.

    Args:
        path: The file path (used for title extraction).
        content: The raw markdown content.

    Returns:
        A Note object with parsed frontmatter and content.
    """
    # Parse frontmatter
    post = frontmatter.loads(content)

    # Extract title from frontmatter, first H1, or filename
    title = _extract_title(path, post.metadata, post.content)

    return Note(
        path=path,
        title=title,
        content=post.content,
        frontmatter=dict(post.metadata),
    )


def _extract_title(path: str, metadata: dict[str, object], content: str) -> str:
    """Extract the note title from various sources.

    Priority:
    1. Frontmatter 'title' field
    2. First H1 heading in content
    3. Filename without extension
    """
    # Check frontmatter
    if "title" in metadata and isinstance(metadata["title"], str):
        return metadata["title"]

    # Check for first H1
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:].strip()

    # Fall back to filename
    return Path(path).stem
