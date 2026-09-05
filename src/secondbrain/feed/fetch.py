"""RSS fetching via feedparser. One dead feed never blocks the batch."""

import logging
from datetime import UTC, datetime
from time import mktime

import feedparser

from secondbrain.feed.models import FeedItem, FeedSource

logger = logging.getLogger(__name__)

_SNIPPET_MAX = 400
# Feed content is attacker-influenced: anyone who can land an entry in a
# subscribed feed controls the link. Only ever store navigable web URLs so a
# "javascript:" or "data:" href can never reach the UI.
_SAFE_SCHEMES = ("http://", "https://")


def _is_safe_link(link: str) -> bool:
    return link.lower().startswith(_SAFE_SCHEMES)


def _entry_published(entry: object) -> str | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    try:
        return datetime.fromtimestamp(mktime(parsed), UTC).isoformat()
    except (ValueError, OverflowError):
        return None


def fetch_source(source: FeedSource) -> list[FeedItem]:
    """Fetch one source; return [] on any error (logged), never raise."""
    try:
        parsed = feedparser.parse(source.url)
    except Exception:
        logger.warning("Feed fetch failed for %s", source.url, exc_info=True)
        return []
    if getattr(parsed, "bozo", 0) and not parsed.entries:
        logger.warning("Feed unparseable/empty: %s", source.url)
        return []
    items: list[FeedItem] = []
    for entry in parsed.entries:
        title = (getattr(entry, "title", "") or "").strip()
        link = (getattr(entry, "link", "") or "").strip()
        if not title or not link:
            continue
        if not _is_safe_link(link):
            logger.warning("Skipping entry with unsafe link scheme from %s", source.label)
            continue
        snippet = (getattr(entry, "summary", "") or "")[:_SNIPPET_MAX]
        items.append(
            FeedItem(
                url=link,
                source_label=source.label,
                type=source.type,
                title=title,
                snippet=snippet,
                published_at=_entry_published(entry),
                trust=source.trust,
            )
        )
    return items


def fetch_all(sources: list[FeedSource]) -> list[FeedItem]:
    """Fetch every source, skipping failures. Sequential (RSS is fast, cron-time)."""
    out: list[FeedItem] = []
    for source in sources:
        items = fetch_source(source)
        logger.info("Fetched %d items from %s", len(items), source.label)
        out.extend(items)
    return out
