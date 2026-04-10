"""Wiki compiler: transform fetched content into structured Obsidian wiki pages."""

from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import anthropic

from secondbrain.ingestion.fetcher import FetchedContent

if TYPE_CHECKING:
    from secondbrain.stores.usage import UsageStore

logger = logging.getLogger(__name__)

COMPILE_MODEL = "claude-haiku-4-5"
MAX_SLUG_LEN = 80

_COMPILE_SYSTEM_PROMPT = (
    "You are a knowledge compiler. Your job is to take raw text from an external source "
    "and transform it into a clean, well-structured Obsidian wiki page.\n\n"
    "Guidelines:\n"
    "- Organize content by topic, NOT in source order.\n"
    "- Use Markdown headings (##, ###) to create clear structure.\n"
    "- Use [[wiki-links]] for key concepts, terms, and related topics.\n"
    "- Write in a neutral, encyclopedic tone.\n"
    "- DO NOT include a title or frontmatter in your output — those are added separately.\n"
    "- DO NOT include a source attribution line — that is added separately.\n"
    "- Start directly with the first heading or paragraph of content."
)

_COMPILE_ANSWER_SYSTEM_PROMPT = (
    "You are a knowledge compiler. Your job is to restructure a chat answer into a "
    "standalone, reference-quality Obsidian wiki page.\n\n"
    "Guidelines:\n"
    "- Remove all conversational phrasing (e.g., 'Great question!', 'As I mentioned...').\n"
    "- Add clear Markdown headings (##, ###) to organize the content.\n"
    "- Use [[wiki-links]] for citation references and key concepts.\n"
    "- Write in a neutral, encyclopedic tone suitable for future reference.\n"
    "- DO NOT include a title or frontmatter in your output — those are added separately.\n"
    "- Start directly with the first heading or paragraph."
)


def slugify_title(title: str) -> str:
    """Convert a title to a filesystem-safe slug.

    Lowercase, remove non-alphanumeric (keep spaces and hyphens),
    collapse multiple hyphens, strip leading/trailing hyphens, truncate to 80 chars.
    """
    slug = title.lower()
    # Replace any character that is not alphanumeric, space, or hyphen
    slug = re.sub(r"[^a-z0-9 \-]", "", slug)
    # Replace spaces with hyphens
    slug = slug.replace(" ", "-")
    # Collapse multiple consecutive hyphens
    slug = re.sub(r"-{2,}", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    # Truncate
    slug = slug[:MAX_SLUG_LEN]
    # Strip again in case truncation left a trailing hyphen
    slug = slug.strip("-")
    return slug


def _today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


def _escape_yaml_str(value: str) -> str:
    """Escape double quotes inside a YAML double-quoted string."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_compile_frontmatter(
    title: str,
    source_url: str,
    source_type: str,
) -> str:
    date = _today_iso()
    return (
        f"---\n"
        f'title: "{_escape_yaml_str(title)}"\n'
        f'source: "{_escape_yaml_str(source_url)}"\n'
        f'source_type: "{_escape_yaml_str(source_type)}"\n'
        f'compiled_date: "{date}"\n'
        f"tags: []\n"
        f"---\n"
    )


def _build_answer_frontmatter(
    title: str,
    query: str,
    citations: list[str],
) -> str:
    date = _today_iso()
    citations_yaml = "\n".join(f'  - "{_escape_yaml_str(c)}"' for c in citations)
    citations_block = f"citations:\n{citations_yaml}" if citations else "citations: []"
    return (
        f"---\n"
        f'title: "{_escape_yaml_str(title)}"\n'
        f'source_type: "synthesis"\n'
        f'query: "{_escape_yaml_str(query)}"\n'
        f'compiled_date: "{date}"\n'
        f"{citations_block}\n"
        f"tags: []\n"
        f"---\n"
    )


class WikiCompiler:
    """Compiles fetched/audited content into structured Obsidian wiki pages."""

    def __init__(
        self,
        api_key: str,
        usage_store: UsageStore | None = None,
    ) -> None:
        self._client = anthropic.Anthropic(
            api_key=api_key,
            timeout=60.0,
        )
        self._usage_store = usage_store

    def compile(
        self,
        content: FetchedContent,
        vault_manifest: str | None = None,
    ) -> tuple[str, str]:
        """Compile fetched content into a wiki page.

        Returns:
            (full_markdown_with_frontmatter, title)
        """
        system_prompt = _COMPILE_SYSTEM_PROMPT
        if vault_manifest:
            system_prompt = (
                f"{_COMPILE_SYSTEM_PROMPT}\n\n"
                f"## Existing Vault Topics (for [[wiki-link]] context)\n\n"
                f"{vault_manifest}"
            )

        user_message = (
            f"Source URL: {content.source_url}\n"
            f"Source Title: {content.title}\n"
            f"Content Type: {content.content_type}\n\n"
            f"Raw Content:\n\n{content.raw_text}"
        )

        start = time.monotonic()
        response = self._client.messages.create(
            model=COMPILE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        latency_ms = (time.monotonic() - start) * 1000

        body = str(getattr(response.content[0], "text", ""))
        title = content.title

        frontmatter = _build_compile_frontmatter(
            title=title,
            source_url=content.source_url,
            source_type=str(content.content_type),
        )
        attribution = f"> Source: [{content.source_url}]({content.source_url})\n\n"
        full_markdown = f"{frontmatter}\n{attribution}{body}"

        self._log_usage(
            model=COMPILE_MODEL,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
        )

        return full_markdown, title

    def compile_answer(
        self,
        answer_text: str,
        query: str,
        citations: list[str],
    ) -> tuple[str, str]:
        """Compile a chat answer into a wiki page (KLIB-3).

        Returns:
            (full_markdown_with_frontmatter, title)
        """
        title = f"Synthesized: {query[:100]}"

        user_message = f"Original query: {query}\n\nChat answer to restructure:\n\n{answer_text}"

        start = time.monotonic()
        response = self._client.messages.create(
            model=COMPILE_MODEL,
            max_tokens=4096,
            system=_COMPILE_ANSWER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        latency_ms = (time.monotonic() - start) * 1000

        body = str(getattr(response.content[0], "text", ""))

        frontmatter = _build_answer_frontmatter(
            title=title,
            query=query,
            citations=citations,
        )
        full_markdown = f"{frontmatter}\n{body}"

        self._log_usage(
            model=COMPILE_MODEL,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
        )

        return full_markdown, title

    def find_existing_by_source(
        self,
        wiki_dir: Path,
        source_url: str,
    ) -> Path | None:
        """Scan wiki_dir for a page whose frontmatter source matches source_url.

        Returns the matching path, or None if not found.
        """
        for md_file in wiki_dir.glob("*.md"):
            text = md_file.read_text(encoding="utf-8")
            if f'source: "{source_url}"' in text:
                return md_file
        return None

    def _log_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ) -> None:
        if self._usage_store is None:
            return
        # Haiku pricing: $0.80/$4.00 per million tokens (input/output)
        cost_usd = (input_tokens / 1_000_000) * 0.80 + (output_tokens / 1_000_000) * 4.00
        self._usage_store.log_usage(
            provider="anthropic",
            model=model,
            usage_type="wiki_compile",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
