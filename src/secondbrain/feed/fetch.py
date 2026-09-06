"""RSS fetching. One dead feed never blocks the batch — and never hangs it.

feedparser is used purely as a parser here, never as a fetcher: its own
``opener.open(request)`` passes no timeout, so a wedged host would block the
daily sync forever (an exception handler cannot catch a hang). We do the HTTP
ourselves with bounded connect/read timeouts and a response size cap.
"""

import calendar
import logging
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx

from secondbrain.feed.models import FeedItem, FeedSource
from secondbrain.feed.text import strip_html

logger = logging.getLogger(__name__)

_SNIPPET_MAX = 400
# Titles are attacker-controlled and were the one unbounded field: an entry
# could carry megabytes of "title" straight into the summarizer prompt, which
# is the single call the whole cost budget rests on.
_TITLE_MAX = 300
# Feed content is attacker-influenced: anyone who can land an entry in a
# subscribed feed controls the link. Only ever store navigable web URLs so a
# "javascript:" or "data:" href can never reach the UI.
_SAFE_SCHEMES = ("http://", "https://")

_CONNECT_TIMEOUT = 5.0
_READ_TIMEOUT = 15.0
_MAX_BYTES = 5 * 1024 * 1024  # a hostile or broken host must not OOM the sync
_USER_AGENT = "SecondBrain/1.0 (+local personal feed reader)"


def _is_safe_link(link: str) -> bool:
    return link.lower().startswith(_SAFE_SCHEMES)


def _redacted(url: str) -> str:
    """Drop any userinfo — feeds may carry basic-auth credentials in the URL."""
    try:
        parts = urlsplit(url)
        return urlunsplit(parts._replace(netloc=parts.hostname or ""))
    except ValueError:
        return "<unparseable url>"


def _entry_published(entry: object) -> str | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    try:
        # published_parsed is a UTC struct_time. time.mktime would read it as
        # LOCAL time, shifting every timestamp by the UTC offset (8h here) and
        # silently flattening recency_decay for anything recent.
        return datetime.fromtimestamp(calendar.timegm(parsed), UTC).isoformat()
    except (ValueError, OverflowError):
        return None


def _download(url: str) -> bytes | None:
    """Fetch feed bytes with bounded time and size. None on any failure."""
    try:
        with httpx.stream(
            "GET",
            url,
            timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > _MAX_BYTES:
                    logger.warning("Feed exceeded %d bytes, truncating: %s", _MAX_BYTES, url)
                    break
                chunks.append(chunk)
            return b"".join(chunks)
    except Exception:
        logger.warning("Feed download failed for %s", _redacted(url), exc_info=True)
        return None


def fetch_source(source: FeedSource) -> list[FeedItem]:
    """Fetch one source; return [] on any error (logged), never raise."""
    if not _is_safe_link(source.url):
        logger.warning("Skipping source with non-http(s) URL: %s", source.label)
        return []
    raw = _download(source.url)
    if raw is None:
        return []
    try:
        parsed = feedparser.parse(raw)
    except Exception:
        logger.warning("Feed parse failed for %s", source.label, exc_info=True)
        return []
    if getattr(parsed, "bozo", 0) and not parsed.entries:
        logger.warning("Feed unparseable/empty: %s", source.label)
        return []
    items: list[FeedItem] = []
    for entry in parsed.entries:
        # Titles carry entities ("&amp;", "&#8217;") and the odd inline tag.
        title = strip_html(getattr(entry, "title", "") or "")[:_TITLE_MAX]
        link = (getattr(entry, "link", "") or "").strip()
        if not title or not link:
            continue
        if not _is_safe_link(link):
            logger.warning("Skipping entry with unsafe link scheme from %s", source.label)
            continue
        snippet = strip_html(getattr(entry, "summary", "") or "")[:_SNIPPET_MAX]
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
