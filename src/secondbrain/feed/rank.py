"""Heuristic feed ranking — deterministic, no LLM. score = trust * interest * recency."""

import math
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from secondbrain.feed.models import FeedItem

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref"}
_RECENCY_HALFLIFE_HOURS = 48.0
# Clock skew and bad publisher dates are common; a little slack is normal, but an
# item dated far in the future must not pin itself at the top of the feed forever.
_FUTURE_SKEW_TOLERANCE_HOURS = 6.0
_UNKNOWN_RECENCY = 0.5


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in _TRACKING_PARAMS]
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().lower()


def dedup_items(items: list[FeedItem]) -> list[FeedItem]:
    """Drop items sharing a normalized URL, or a normalized title within one source.

    Title matching is scoped per source on purpose: recurring column titles
    ("Unverified Voracity", "Padres Injury Report") are genuinely different
    stories across days, and a global title key would collapse them into one.
    """
    seen_urls: set[str] = set()
    seen_titles: set[tuple[str, str]] = set()
    out: list[FeedItem] = []
    for it in items:
        url_key = normalize_url(it.url)
        title_key = (it.source_label, normalize_title(it.title))
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        out.append(it)
    return out


def _parse_epoch(published_at: str | None) -> float | None:
    if not published_at:
        return None
    try:
        return datetime.fromisoformat(published_at).timestamp()
    except ValueError:
        return None


def recency_decay(published_ts_or_iso: float | str | None, now_ts: float) -> float:
    """Exponential decay by age; unknown or implausible date -> 0.5 (neutral)."""
    ts = published_ts_or_iso
    if isinstance(ts, str) or ts is None:
        ts = _parse_epoch(ts if isinstance(ts, str) else None)
    if ts is None:
        return _UNKNOWN_RECENCY
    age_hours = (now_ts - ts) / 3600.0
    if age_hours < -_FUTURE_SKEW_TOLERANCE_HOURS:
        # Dated well into the future: treat as unknown rather than maximally fresh,
        # so a broken publisher clock can't camp at the top of the feed.
        return _UNKNOWN_RECENCY
    return math.pow(0.5, max(0.0, age_hours) / _RECENCY_HALFLIFE_HOURS)


def _interest_patterns(interests: dict[str, float]) -> list[tuple[re.Pattern[str], float]]:
    """Compile once per ranking pass. Word-bounded so "rag" doesn't match
    "storage" and "eval" doesn't match "medieval"."""
    return [
        (re.compile(rf"\b{re.escape(kw.lower())}\b"), weight)
        for kw, weight in interests.items()
        if kw.strip()
    ]


def score_item(item: FeedItem, interests: dict[str, float], now_ts: float) -> float:
    return _score_with(item, _interest_patterns(interests), now_ts)


def _score_with(
    item: FeedItem, patterns: list[tuple[re.Pattern[str], float]], now_ts: float
) -> float:
    haystack = f"{item.title} {item.snippet}".lower()
    interest_match = 1.0 + sum(w for pattern, w in patterns if pattern.search(haystack))
    return item.trust * interest_match * recency_decay(item.published_at, now_ts)


def rank_items(
    items: list[FeedItem], interests: dict[str, float], now_ts: float | None = None
) -> list[FeedItem]:
    now = now_ts if now_ts is not None else datetime.now(UTC).timestamp()
    patterns = _interest_patterns(interests)
    for it in items:
        it.score = _score_with(it, patterns, now)
    return sorted(items, key=lambda i: i.score, reverse=True)


def select_top_n(
    ranked: list[FeedItem],
    n: int,
    min_per_type: int,
    types: tuple[str, ...] = ("ai", "sports"),
) -> list[FeedItem]:
    """Top-N by score, but guarantee `min_per_type` slots for each listed type (best-effort when infeasible)."""
    chosen: list[FeedItem] = []
    chosen_urls: set[str] = set()
    for t in types:
        if len(chosen) >= n:
            break
        for it in [i for i in ranked if i.type == t][:min_per_type]:
            if len(chosen) >= n:
                break
            if it.url not in chosen_urls:
                chosen.append(it)
                chosen_urls.add(it.url)
    for it in ranked:
        if len(chosen) >= n:
            break
        if it.url not in chosen_urls:
            chosen.append(it)
            chosen_urls.add(it.url)
    return sorted(chosen, key=lambda i: i.score, reverse=True)[:n]
