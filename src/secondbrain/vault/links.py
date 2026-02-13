"""Wiki link parser for Obsidian [[wiki links]]."""

import re

# Match [[target]] or [[target|alias]] or [[target#heading]] or [[target#heading|alias]]
_WIKI_LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]")

# Match fenced code blocks (```...```)
_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```")

# Match inline code (`...`)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")


def extract_wiki_links(text: str) -> list[str]:
    """Extract [[wiki link]] targets from markdown text.

    Handles: [[Note]], [[Note|alias]], [[Note#heading]], [[Note#heading|alias]]
    Excludes links inside code blocks (backtick-fenced).
    Returns deduplicated list of target titles.
    """
    # Strip code blocks before parsing
    cleaned = _FENCED_CODE_RE.sub("", text)
    cleaned = _INLINE_CODE_RE.sub("", cleaned)

    targets: list[str] = []
    seen: set[str] = set()
    for match in _WIKI_LINK_RE.finditer(cleaned):
        title = match.group(1).strip()
        if title and title not in seen:
            seen.add(title)
            targets.append(title)

    return targets
