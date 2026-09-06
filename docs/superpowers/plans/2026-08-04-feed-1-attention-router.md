# FEED-1 Attention Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A cheap, personalized daily RSS feed (AI + sports) that ingests headlines for free, ranks with heuristics, spends one batched Haiku call/day on the top items, and surfaces them on the Today surface + a `/feed` page — all behind a `feed_enabled` flag.

**Architecture:** A `filter-before-you-spend` pipeline in a new `secondbrain/feed/` package: `config` (vault-note sources/interests) → `fetch` (feedparser, defensive) → `rank` (heuristic, no LLM) → `summarize` (one batched Anthropic Haiku call, logged to UsageStore) → `FeedStore` (transient SQLite, 30-day prune). A daily-sync `feed` command runs the pipeline; the briefing/digest fold in a feed count; a `/feed` page + Today-surface block render it.

**Tech Stack:** Python 3.12, `feedparser` (new dep), `python-frontmatter` (present), `anthropic` (present), SQLite (WAL), FastAPI, Next.js/React.

**Verification note:** Run Python via `uv run python -m pytest ...` (NOT `uv run pytest` — that resolves to Anaconda's pytest). After backend changes, restart the API launchd service per CLAUDE.md before manual QA.

---

## File Structure

**Create:**
- `src/secondbrain/feed/__init__.py` — package marker
- `src/secondbrain/feed/models.py` — `FeedSource`, `FeedConfig`, `FeedItem`, `FeedSection`, `FeedSummary` dataclasses
- `src/secondbrain/feed/config.py` — `SEED_DEFAULTS`, `parse_feed_config(text)`, `load_feed_config(vault_path, rel_path)`
- `src/secondbrain/feed/fetch.py` — `fetch_source(source, timeout)`, `fetch_all(sources)`
- `src/secondbrain/feed/rank.py` — `normalize_url`, `normalize_title`, `dedup_items`, `recency_decay`, `score_item`, `rank_items`, `select_top_n`
- `src/secondbrain/feed/summarize.py` — `build_summary_prompt`, `parse_summary_response`, `summarize_items`
- `src/secondbrain/feed/pipeline.py` — `run_feed_pipeline(vault_path, settings)`
- `src/secondbrain/stores/feed.py` — `FeedStore`
- `src/secondbrain/api/feed.py` — `GET /api/v1/feed`, `POST /api/v1/feed/{item_id}/click`
- `frontend/src/app/(dashboard)/feed/page.tsx` — Feed page
- `frontend/src/components/briefing/FeedBlock.tsx` — Today-surface feed block
- Tests: `tests/unit/feed/test_config.py`, `test_rank.py`, `test_summarize.py`, `test_store_feed.py`, `test_pipeline.py`, `tests/unit/api/test_feed_digest.py`

**Modify:**
- `src/secondbrain/config.py` — add feed settings (Task 1)
- `src/secondbrain/models.py` — add feed Pydantic response models + `feed_counts` on `BriefingResponse` (Task 8)
- `src/secondbrain/api/briefing.py` — populate feed on briefing, add digest segment (Task 8)
- `src/secondbrain/main.py` — register the feed router (Task 7)
- `src/secondbrain/scripts/daily_sync.py` — add `feed` command + `all` step (Task 6)
- `frontend/src/components/layout/Sidebar.tsx` — toolsNavItems + NAV_COLORS (Task 9)
- `frontend/src/components/layout/MobileNav.tsx` — moreItems (Task 9)
- `frontend/src/components/briefing/MorningBriefing.tsx` — render `<FeedBlock/>` (Task 9)
- `pyproject.toml` — add `feedparser` (Task 0)

---

## Task 0: Dependency + feature flag config

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/secondbrain/config.py:69-72`

- [ ] **Step 1: Add feedparser**

```bash
uv add feedparser
uv run python -c "import feedparser; print(feedparser.__version__)"
```
Expected: prints a version (e.g. `6.0.x`).

- [ ] **Step 2: Add feed settings to Settings** (after `context_generation_enabled` at line 72)

```python
    # Feed (FEED-1 attention router) — off by default so repo cloners aren't affected
    feed_enabled: bool = False
    feed_config_path: str = "_config/feed.md"  # vault-relative sources/interests note
    feed_db_name: str = "feed.db"
    feed_retention_days: int = 30
    feed_summary_model: str = "claude-haiku-4-5"
    feed_top_n: int = 10          # items sent to the one summary call
    feed_min_per_type: int = 3    # guaranteed slots per type so one domain can't crowd out the other
```

- [ ] **Step 3: Verify import**

Run: `uv run python -c "from secondbrain.config import Settings; s=Settings(); print(s.feed_enabled, s.feed_top_n)"`
Expected: `False 10`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock src/secondbrain/config.py
git commit -m "feat(feed): add feedparser dep + feed_enabled config flags"
```

---

## Task 1: Feed models + vault config reader

**Files:**
- Create: `src/secondbrain/feed/__init__.py` (empty)
- Create: `src/secondbrain/feed/models.py`
- Create: `src/secondbrain/feed/config.py`
- Test: `tests/unit/feed/test_config.py`

- [ ] **Step 1: Write models.py**

```python
"""Feed domain models (dataclasses — transient, not vault content)."""

from dataclasses import dataclass, field


@dataclass
class FeedSource:
    url: str
    label: str
    type: str  # "ai" | "sports" | "general"
    trust: float = 0.5


@dataclass
class FeedConfig:
    sources: list[FeedSource]
    interests: dict[str, float]  # keyword -> weight


@dataclass
class FeedItem:
    url: str
    source_label: str
    type: str
    title: str
    snippet: str
    published_at: str | None = None  # ISO 8601 or None
    trust: float = 0.5
    score: float = 0.0
    summary: str | None = None


@dataclass
class FeedSection:
    heading: str  # "AI" | "Sports"
    items: list[dict] = field(default_factory=list)  # {title, url, take}


@dataclass
class FeedSummary:
    sections: list[FeedSection]
    generated: bool  # False when the LLM call failed and we fell back to headlines
```

- [ ] **Step 2: Write the failing test for config parsing**

`tests/unit/feed/__init__.py` (empty), then `tests/unit/feed/test_config.py`:

```python
from secondbrain.feed.config import SEED_DEFAULTS, load_feed_config, parse_feed_config


def test_parse_valid_frontmatter():
    text = """---
sources:
  - url: https://example.com/feed
    label: Example
    type: ai
    trust: 0.9
interests:
  agents: 2.0
  padres: 1.5
---
Notes below frontmatter are ignored.
"""
    cfg = parse_feed_config(text)
    assert len(cfg.sources) == 1
    assert cfg.sources[0].url == "https://example.com/feed"
    assert cfg.sources[0].trust == 0.9
    assert cfg.interests["agents"] == 2.0


def test_parse_malformed_falls_back_to_defaults():
    cfg = parse_feed_config("not: [valid: yaml: at all")
    assert cfg.sources == SEED_DEFAULTS.sources


def test_parse_missing_keys_falls_back():
    cfg = parse_feed_config("---\nunrelated: true\n---\n")
    assert cfg.sources == SEED_DEFAULTS.sources


def test_load_missing_file_returns_defaults(tmp_path):
    cfg = load_feed_config(tmp_path, "_config/feed.md")
    assert cfg.sources == SEED_DEFAULTS.sources


def test_seed_defaults_have_both_types():
    types = {s.type for s in SEED_DEFAULTS.sources}
    assert "ai" in types and "sports" in types
```

- [ ] **Step 3: Run it — expect failure**

Run: `uv run python -m pytest tests/unit/feed/test_config.py -v`
Expected: FAIL (module `secondbrain.feed.config` not found).

- [ ] **Step 4: Write config.py**

```python
"""Feed source/interest config — vault-as-truth with built-in seed defaults.

Reads a vault note (default ``_config/feed.md``) whose frontmatter lists sources
and interests. Missing or malformed config falls back to seed defaults; never crashes.
Source RSS URLs are verified live during implementation (Task 3 manual QA).
"""

import logging
from pathlib import Path

import frontmatter

from secondbrain.feed.models import FeedConfig, FeedSource

logger = logging.getLogger(__name__)

SEED_DEFAULTS = FeedConfig(
    sources=[
        # AI — blogs + newsletters (free RSS, high signal). Verify each is live.
        FeedSource("https://simonwillison.net/atom/everything/", "Simon Willison", "ai", 0.9),
        FeedSource("https://www.latent.space/feed", "Latent Space", "ai", 0.8),
        FeedSource("https://importai.substack.com/feed", "Import AI", "ai", 0.8),
        FeedSource("https://www.deeplearning.ai/the-batch/rss/", "The Batch", "ai", 0.8),
        FeedSource("https://www.anthropic.com/rss.xml", "Anthropic News", "ai", 0.7),
        # Sports — team-specific where it exists, league-level fallback. Verify each.
        FeedSource("https://www.mlb.com/padres/feeds/news/rss.xml", "Padres", "sports", 0.8),
        FeedSource("https://mgoblog.com/rss.xml", "Michigan FB (MGoBlog)", "sports", 0.7),
        FeedSource("https://www.espn.com/espn/rss/nfl/news", "NFL (ESPN)", "sports", 0.6),
    ],
    interests={
        # AI
        "agents": 2.0, "anthropic": 2.0, "claude": 1.8, "llm": 1.5, "rag": 1.5,
        "openai": 1.2, "model": 1.0, "eval": 1.2, "prompt": 1.0,
        # Sports
        "padres": 2.0, "michigan": 2.0, "wolverines": 1.8, "nfl": 1.2, "playoff": 1.2,
    },
)


def parse_feed_config(text: str) -> FeedConfig:
    """Parse frontmatter text into a FeedConfig, falling back to defaults on any problem."""
    try:
        post = frontmatter.loads(text)
        raw_sources = post.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            return SEED_DEFAULTS
        sources = [
            FeedSource(
                url=str(s["url"]),
                label=str(s.get("label", s["url"])),
                type=str(s.get("type", "general")),
                trust=float(s.get("trust", 0.5)),
            )
            for s in raw_sources
            if isinstance(s, dict) and s.get("url")
        ]
        if not sources:
            return SEED_DEFAULTS
        raw_interests = post.get("interests") or {}
        interests = {
            str(k): float(v)
            for k, v in raw_interests.items()
            if isinstance(raw_interests, dict)
        }
        return FeedConfig(sources=sources, interests=interests)
    except Exception:
        logger.warning("Feed config parse failed; using seed defaults", exc_info=True)
        return SEED_DEFAULTS


def load_feed_config(vault_path: Path, rel_path: str) -> FeedConfig:
    """Load feed config from a vault note; seed defaults if absent/unreadable."""
    config_file = vault_path / rel_path
    if not config_file.exists():
        logger.info("No feed config at %s; using seed defaults", config_file)
        return SEED_DEFAULTS
    try:
        return parse_feed_config(config_file.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Could not read feed config %s; using defaults", config_file, exc_info=True)
        return SEED_DEFAULTS
```

- [ ] **Step 5: Run tests — expect pass**

Run: `uv run python -m pytest tests/unit/feed/test_config.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/secondbrain/feed/ tests/unit/feed/
git commit -m "feat(feed): domain models + vault config reader with seed defaults"
```

---

## Task 2: Ranker (pure, no LLM)

**Files:**
- Create: `src/secondbrain/feed/rank.py`
- Test: `tests/unit/feed/test_rank.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/feed/test_rank.py`:

```python
from secondbrain.feed.models import FeedItem
from secondbrain.feed.rank import (
    dedup_items,
    normalize_title,
    normalize_url,
    rank_items,
    recency_decay,
    score_item,
    select_top_n,
)

NOW = 1_700_000_000.0  # fixed reference epoch seconds


def _item(url, title, type="ai", trust=0.5, snippet="", published=None):
    return FeedItem(url=url, source_label="s", type=type, title=title,
                    snippet=snippet, published_at=published, trust=trust)


def test_normalize_url_strips_tracking_and_trailing_slash():
    assert normalize_url("https://x.com/a/?utm_source=rss&id=1") == "https://x.com/a?id=1"
    assert normalize_url("https://x.com/a/") == "https://x.com/a"


def test_normalize_title_lowercases_and_collapses_space():
    assert normalize_title("  Big   NEWS! ") == "big news!"


def test_dedup_by_url_and_title():
    items = [
        _item("https://x.com/a/", "Hello"),
        _item("https://x.com/a", "Hello"),        # same after normalize
        _item("https://x.com/b", "Hello"),         # same title, different url -> dup
        _item("https://x.com/c", "Different"),
    ]
    out = dedup_items(items)
    assert len(out) == 2


def test_recency_decay_favors_recent():
    recent = recency_decay(NOW - 3600, NOW)     # 1h old
    old = recency_decay(NOW - 3600 * 96, NOW)   # 96h old
    assert recent > old
    assert recency_decay(None, NOW) == 0.5      # unknown date -> neutral-ish


def test_score_rewards_interest_hits():
    interests = {"agents": 2.0}
    hit = _item("u1", "New agents framework", trust=1.0)
    miss = _item("u2", "Unrelated headline", trust=1.0)
    assert score_item(hit, interests, NOW) > score_item(miss, interests, NOW)


def test_rank_orders_descending():
    interests = {"agents": 2.0}
    items = [_item("u1", "boring", trust=0.5), _item("u2", "agents agents", trust=1.0)]
    ranked = rank_items(items, interests, now_ts=NOW)
    assert ranked[0].url == "u2"
    assert ranked[0].score >= ranked[1].score


def test_select_top_n_enforces_per_type_minimum():
    # 8 AI items outscore all sports; min_per_type must still pull sports in.
    ai = [_item(f"ai{i}", "agents", type="ai", trust=1.0) for i in range(8)]
    sports = [_item(f"sp{i}", "padres", type="sports", trust=0.2) for i in range(3)]
    interests = {"agents": 5.0, "padres": 0.1}
    ranked = rank_items(ai + sports, interests, now_ts=NOW)
    top = select_top_n(ranked, n=6, min_per_type=2, types=("ai", "sports"))
    assert len(top) == 6
    assert sum(1 for i in top if i.type == "sports") >= 2
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run python -m pytest tests/unit/feed/test_rank.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write rank.py**

```python
"""Heuristic feed ranking — deterministic, no LLM. score = trust * interest * recency."""

import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from secondbrain.feed.models import FeedItem

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref"}
_RECENCY_HALFLIFE_HOURS = 48.0


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in _TRACKING_PARAMS]
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().lower()


def dedup_items(items: list[FeedItem]) -> list[FeedItem]:
    """Drop items sharing a normalized URL or a normalized title (first wins)."""
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    out: list[FeedItem] = []
    for it in items:
        u, t = normalize_url(it.url), normalize_title(it.title)
        if u in seen_urls or t in seen_titles:
            continue
        seen_urls.add(u)
        seen_titles.add(t)
        out.append(it)
    return out


def _parse_epoch(published_at: str | None) -> float | None:
    if not published_at:
        return None
    try:
        return datetime.fromisoformat(published_at).timestamp()
    except ValueError:
        return None


def recency_decay(published_ts_or_iso, now_ts: float) -> float:
    """Exponential decay by age; unknown date -> 0.5 (neutral)."""
    ts = published_ts_or_iso
    if isinstance(ts, str) or ts is None:
        ts = _parse_epoch(ts if isinstance(ts, str) else None)
    if ts is None:
        return 0.5
    age_hours = max(0.0, (now_ts - ts) / 3600.0)
    return 0.5 ** (age_hours / _RECENCY_HALFLIFE_HOURS)


def score_item(item: FeedItem, interests: dict[str, float], now_ts: float) -> float:
    haystack = f"{item.title} {item.snippet}".lower()
    interest_match = 1.0 + sum(w for kw, w in interests.items() if kw.lower() in haystack)
    return item.trust * interest_match * recency_decay(item.published_at, now_ts)


def rank_items(items: list[FeedItem], interests: dict[str, float], now_ts: float | None = None) -> list[FeedItem]:
    now = now_ts if now_ts is not None else datetime.now(UTC).timestamp()
    for it in items:
        it.score = score_item(it, interests, now)
    return sorted(items, key=lambda i: i.score, reverse=True)


def select_top_n(
    ranked: list[FeedItem],
    n: int,
    min_per_type: int,
    types: tuple[str, ...] = ("ai", "sports"),
) -> list[FeedItem]:
    """Top-N by score, but guarantee `min_per_type` slots for each listed type."""
    chosen: list[FeedItem] = []
    chosen_urls: set[str] = set()
    for t in types:
        for it in [i for i in ranked if i.type == t][:min_per_type]:
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
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run python -m pytest tests/unit/feed/test_rank.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/feed/rank.py tests/unit/feed/test_rank.py
git commit -m "feat(feed): heuristic ranker (dedup, recency decay, per-type top-N)"
```

---

## Task 3: Fetcher (feedparser, defensive)

**Files:**
- Create: `src/secondbrain/feed/fetch.py`
- Test: `tests/unit/feed/test_fetch.py`

- [ ] **Step 1: Write fetch.py**

```python
"""RSS fetching via feedparser. One dead feed never blocks the batch."""

import logging
from datetime import UTC, datetime
from time import mktime

import feedparser

from secondbrain.feed.models import FeedItem, FeedSource

logger = logging.getLogger(__name__)

_SNIPPET_MAX = 400


def _entry_published(entry) -> str | None:
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
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link:
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
        got = fetch_source(source)
        logger.info("Fetched %d items from %s", len(got), source.label)
        out.extend(got)
    return out
```

- [ ] **Step 2: Write test using a monkeypatched feedparser**

`tests/unit/feed/test_fetch.py`:

```python
from types import SimpleNamespace

from secondbrain.feed import fetch as fetch_mod
from secondbrain.feed.models import FeedSource


def _fake_parsed(entries, bozo=0):
    return SimpleNamespace(entries=entries, bozo=bozo)


def test_fetch_source_maps_entries(monkeypatch):
    entry = SimpleNamespace(title="Hello", link="https://x.com/a", summary="body",
                            published_parsed=(2026, 8, 4, 12, 0, 0, 0, 0, 0))
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda url: _fake_parsed([entry]))
    items = fetch_mod.fetch_source(FeedSource("u", "Lbl", "ai", 0.9))
    assert len(items) == 1
    assert items[0].title == "Hello"
    assert items[0].trust == 0.9
    assert items[0].published_at is not None


def test_fetch_source_skips_entries_missing_title_or_link(monkeypatch):
    entries = [SimpleNamespace(title="", link="u", summary=""),
               SimpleNamespace(title="t", link="", summary="")]
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda url: _fake_parsed(entries))
    assert fetch_mod.fetch_source(FeedSource("u", "L", "ai")) == []


def test_fetch_source_returns_empty_on_exception(monkeypatch):
    def boom(url):
        raise RuntimeError("network down")
    monkeypatch.setattr(fetch_mod.feedparser, "parse", boom)
    assert fetch_mod.fetch_source(FeedSource("u", "L", "ai")) == []


def test_fetch_all_continues_past_failures(monkeypatch):
    def parse(url):
        if url == "bad":
            raise RuntimeError("down")
        return _fake_parsed([SimpleNamespace(title="t", link="https://x/1", summary="")])
    monkeypatch.setattr(fetch_mod.feedparser, "parse", parse)
    sources = [FeedSource("bad", "B", "ai"), FeedSource("good", "G", "ai")]
    assert len(fetch_mod.fetch_all(sources)) == 1
```

- [ ] **Step 3: Run — expect pass**

Run: `uv run python -m pytest tests/unit/feed/test_fetch.py -v`
Expected: 4 passed.

- [ ] **Step 4: Verify seed feeds are live** (manual, informational — fix dead URLs in `SEED_DEFAULTS`)

Run: `uv run python -c "from secondbrain.feed.config import SEED_DEFAULTS; from secondbrain.feed.fetch import fetch_all; items=fetch_all(SEED_DEFAULTS.sources); print(len(items), 'items'); [print(s.label, len([i for i in items if i.source_label==s.label])) for s in SEED_DEFAULTS.sources]"`
Expected: a per-source count. Any source showing `0` has a dead/wrong RSS URL — correct it in `config.py:SEED_DEFAULTS` and re-run. Note corrections in the commit.

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/feed/fetch.py tests/unit/feed/test_fetch.py src/secondbrain/feed/config.py
git commit -m "feat(feed): defensive feedparser fetcher + verify seed feeds live"
```

---

## Task 4: Summarizer (one batched Haiku call)

**Files:**
- Create: `src/secondbrain/feed/summarize.py`
- Test: `tests/unit/feed/test_summarize.py`

- [ ] **Step 1: Write summarize.py**

```python
"""Batched daily feed summary — exactly one Anthropic Haiku call, logged to UsageStore.

On any failure, falls back to headlines (generated=False) so the feed still works.
"""

import json
import logging
import time

import anthropic

from secondbrain.config import Settings
from secondbrain.feed.models import FeedItem, FeedSection, FeedSummary
from secondbrain.stores.usage import UsageStore, calculate_cost

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a terse news editor. Group the provided items into sections by their "
    "type (AI, Sports). For each item write a one-line take (<=20 words). "
    "Respond with ONLY JSON: "
    '{"sections":[{"heading":"AI","items":[{"url":"...","title":"...","take":"..."}]}]}'
)


def build_summary_prompt(items: list[FeedItem]) -> str:
    lines = [
        f"- [{it.type}] ({it.source_label}) {it.title} :: {it.snippet[:200]} <{it.url}>"
        for it in items
    ]
    return "Items:\n" + "\n".join(lines)


def _fallback(items: list[FeedItem]) -> FeedSummary:
    by_type: dict[str, list[dict]] = {}
    for it in items:
        by_type.setdefault(it.type, []).append(
            {"url": it.url, "title": it.title, "take": it.snippet[:120]}
        )
    sections = [FeedSection(heading=t.upper(), items=v) for t, v in by_type.items()]
    return FeedSummary(sections=sections, generated=False)


def parse_summary_response(text: str, items: list[FeedItem]) -> FeedSummary:
    """Parse model JSON; on any problem, fall back to headlines."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        data = json.loads(text[start:end])
        sections = [
            FeedSection(
                heading=str(s.get("heading", "")),
                items=[
                    {"url": str(i.get("url", "")), "title": str(i.get("title", "")),
                     "take": str(i.get("take", ""))}
                    for i in s.get("items", [])
                ],
            )
            for s in data.get("sections", [])
        ]
        if not sections:
            return _fallback(items)
        return FeedSummary(sections=sections, generated=True)
    except Exception:
        logger.warning("Feed summary parse failed; falling back to headlines", exc_info=True)
        return _fallback(items)


def summarize_items(
    items: list[FeedItem], settings: Settings, usage_store: UsageStore | None = None
) -> FeedSummary:
    """One batched Haiku call over top items. Fallback to headlines on any failure."""
    if not items:
        return FeedSummary(sections=[], generated=False)
    if not settings.anthropic_api_key:
        logger.info("No anthropic_api_key; feed summary falls back to headlines")
        return _fallback(items)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=60.0)
    model = settings.feed_summary_model
    start = time.time()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": build_summary_prompt(items)}],
        )
    except Exception:
        logger.warning("Feed summary LLM call failed; using headlines", exc_info=True)
        return _fallback(items)

    latency_ms = (time.time() - start) * 1000
    text = str(getattr(resp.content[0], "text", ""))
    if usage_store is not None:
        in_tok, out_tok = resp.usage.input_tokens, resp.usage.output_tokens
        usage_store.log_usage(
            provider="anthropic",
            model=model,
            usage_type="feed_summary",
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=calculate_cost("anthropic", model, in_tok, out_tok),
            latency_ms=latency_ms,
        )
    return parse_summary_response(text, items)
```

- [ ] **Step 2: Write tests**

`tests/unit/feed/test_summarize.py`:

```python
from secondbrain.feed.models import FeedItem
from secondbrain.feed.summarize import build_summary_prompt, parse_summary_response


def _item(url="u", title="t", type="ai"):
    return FeedItem(url=url, source_label="s", type=type, title=title, snippet="snip")


def test_prompt_includes_type_and_url():
    p = build_summary_prompt([_item(url="https://x/1", title="Agents", type="ai")])
    assert "[ai]" in p and "https://x/1" in p and "Agents" in p


def test_parse_valid_json():
    items = [_item()]
    text = 'prose {"sections":[{"heading":"AI","items":[{"url":"u","title":"t","take":"hot"}]}]} more'
    s = parse_summary_response(text, items)
    assert s.generated is True
    assert s.sections[0].heading == "AI"
    assert s.sections[0].items[0]["take"] == "hot"


def test_parse_garbage_falls_back():
    items = [_item(type="sports")]
    s = parse_summary_response("no json here", items)
    assert s.generated is False
    assert s.sections[0].heading == "SPORTS"


def test_parse_empty_sections_falls_back():
    s = parse_summary_response('{"sections":[]}', [_item()])
    assert s.generated is False
```

- [ ] **Step 3: Run — expect pass**

Run: `uv run python -m pytest tests/unit/feed/test_summarize.py -v`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add src/secondbrain/feed/summarize.py tests/unit/feed/test_summarize.py
git commit -m "feat(feed): batched Haiku summarizer w/ UsageStore logging + headline fallback"
```

---

## Task 5: FeedStore (transient SQLite)

**Files:**
- Create: `src/secondbrain/stores/feed.py`
- Test: `tests/unit/feed/test_store_feed.py`

- [ ] **Step 1: Write feed.py** (follows `stores/usage.py` skeleton: WAL, busy_timeout, reconnect)

```python
"""Transient feed item store (SQLite, WAL). Items are derived data, pruned at 30 days."""

import contextlib
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from secondbrain.feed.models import FeedItem

logger = logging.getLogger(__name__)


class FeedStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._init_schema()
        return self._conn

    def _reconnect(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS feed_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                source_label TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                snippet TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                summary TEXT,
                shown_at TEXT,
                clicked_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_feed_score ON feed_items(score DESC);
            CREATE INDEX IF NOT EXISTS idx_feed_fetched ON feed_items(fetched_at);
        """)
        self.conn.commit()

    def add_items(self, items: list[FeedItem]) -> int:
        """Insert new items (INSERT OR IGNORE on url). Returns count newly inserted."""
        now = datetime.now(UTC).isoformat()
        before = self.conn.total_changes
        for it in items:
            self.conn.execute(
                """INSERT OR IGNORE INTO feed_items
                   (url, source_label, type, title, snippet, published_at, fetched_at, score, summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (it.url, it.source_label, it.type, it.title, it.snippet,
                 it.published_at, now, it.score, it.summary),
            )
        self.conn.commit()
        return self.conn.total_changes - before

    def update_summaries(self, items: list[FeedItem]) -> None:
        for it in items:
            if it.summary is not None:
                self.conn.execute(
                    "UPDATE feed_items SET summary = ?, score = ? WHERE url = ?",
                    (it.summary, it.score, it.url),
                )
        self.conn.commit()

    def get_recent(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM feed_items ORDER BY score DESC, fetched_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_shown(self, urls: list[str]) -> None:
        now = datetime.now(UTC).isoformat()
        for u in urls:
            self.conn.execute(
                "UPDATE feed_items SET shown_at = COALESCE(shown_at, ?) WHERE url = ?", (now, u)
            )
        self.conn.commit()

    def mark_clicked(self, item_id: int) -> str | None:
        now = datetime.now(UTC).isoformat()
        row = self.conn.execute("SELECT url FROM feed_items WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return None
        self.conn.execute("UPDATE feed_items SET clicked_at = ? WHERE id = ?", (now, item_id))
        self.conn.commit()
        return str(row["url"])

    def prune_old(self, days: int = 30) -> int:
        cur = self.conn.execute(
            "DELETE FROM feed_items WHERE fetched_at < datetime('now', ?)", (f"-{days} days",)
        )
        self.conn.commit()
        return cur.rowcount

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
```

- [ ] **Step 2: Write tests**

`tests/unit/feed/test_store_feed.py`:

```python
from secondbrain.feed.models import FeedItem
from secondbrain.stores.feed import FeedStore


def _item(url, title="t", type="ai", score=1.0, summary=None):
    return FeedItem(url=url, source_label="s", type=type, title=title,
                    snippet="snip", score=score, summary=summary)


def test_add_dedups_on_url(tmp_path):
    store = FeedStore(tmp_path / "feed.db")
    assert store.add_items([_item("https://x/1")]) == 1
    assert store.add_items([_item("https://x/1")]) == 0  # same url ignored
    assert len(store.get_recent()) == 1


def test_get_recent_orders_by_score(tmp_path):
    store = FeedStore(tmp_path / "feed.db")
    store.add_items([_item("u1", score=0.1), _item("u2", score=0.9)])
    rows = store.get_recent()
    assert rows[0]["url"] == "u2"


def test_update_summaries(tmp_path):
    store = FeedStore(tmp_path / "feed.db")
    store.add_items([_item("u1")])
    it = _item("u1", score=2.0, summary="hot take")
    store.update_summaries([it])
    assert store.get_recent()[0]["summary"] == "hot take"


def test_mark_clicked_returns_url(tmp_path):
    store = FeedStore(tmp_path / "feed.db")
    store.add_items([_item("https://x/click")])
    row_id = store.get_recent()[0]["id"]
    assert store.mark_clicked(row_id) == "https://x/click"
    assert store.get_recent()[0]["clicked_at"] is not None
    assert store.mark_clicked(99999) is None


def test_prune_old_keeps_fresh(tmp_path):
    store = FeedStore(tmp_path / "feed.db")
    store.add_items([_item("u1")])  # fetched_at = now
    assert store.prune_old(days=30) == 0
    assert len(store.get_recent()) == 1
```

- [ ] **Step 3: Run — expect pass**

Run: `uv run python -m pytest tests/unit/feed/test_store_feed.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add src/secondbrain/stores/feed.py tests/unit/feed/test_store_feed.py
git commit -m "feat(feed): FeedStore — transient SQLite w/ dedup, click tracking, 30d prune"
```

---

## Task 6: Pipeline + daily-sync integration

**Files:**
- Create: `src/secondbrain/feed/pipeline.py`
- Modify: `src/secondbrain/scripts/daily_sync.py:133` (command choices) and `:187` (add step before inbox)
- Test: `tests/unit/feed/test_pipeline.py`

- [ ] **Step 1: Write pipeline.py**

```python
"""Feed pipeline: config -> fetch -> dedup -> rank -> persist -> summarize -> prune."""

import logging
from pathlib import Path

from secondbrain.config import Settings
from secondbrain.feed.config import load_feed_config
from secondbrain.feed.fetch import fetch_all
from secondbrain.feed.rank import dedup_items, rank_items, select_top_n
from secondbrain.feed.summarize import summarize_items
from secondbrain.stores.feed import FeedStore
from secondbrain.stores.usage import UsageStore

logger = logging.getLogger(__name__)


def run_feed_pipeline(vault_path: Path, settings: Settings) -> str:
    """Run the full feed refresh. Returns a one-line summary for logs."""
    if not settings.feed_enabled:
        return "Feed disabled (feed_enabled=False)"

    config = load_feed_config(vault_path, settings.feed_config_path)
    raw = fetch_all(config.sources)
    unique = dedup_items(raw)
    ranked = rank_items(unique, config.interests)

    data_path = Path(settings.data_path)
    store = FeedStore(data_path / settings.feed_db_name)
    try:
        store.add_items(ranked)  # persist full ranked list (cheap rows)
        top = select_top_n(ranked, settings.feed_top_n, settings.feed_min_per_type)
        usage_store = UsageStore(data_path / "usage.db")
        try:
            summary = summarize_items(top, settings, usage_store)
        finally:
            usage_store.close()
        # attach section takes back onto the top items by url, then persist
        takes = {i["url"]: i.get("take") for s in summary.sections for i in s.items}
        for it in top:
            if takes.get(it.url):
                it.summary = takes[it.url]
        store.update_summaries(top)
        store.mark_shown([it.url for it in top])
        pruned = store.prune_old(settings.feed_retention_days)
    finally:
        store.close()

    return (
        f"Feed: {len(raw)} fetched, {len(unique)} unique, {len(top)} summarized "
        f"(generated={summary.generated}), {pruned} pruned"
    )
```

- [ ] **Step 2: Write a pipeline test with monkeypatched fetch + summarize**

`tests/unit/feed/test_pipeline.py`:

```python
from secondbrain.config import Settings
from secondbrain.feed import pipeline as pipe
from secondbrain.feed.models import FeedItem, FeedSummary


def test_disabled_short_circuits(tmp_path):
    s = Settings(feed_enabled=False)
    assert "disabled" in pipe.run_feed_pipeline(tmp_path, s)


def test_pipeline_runs_and_persists(tmp_path, monkeypatch):
    items = [FeedItem(url=f"u{i}", source_label="s", type="ai", title="agents", snippet="") for i in range(4)]
    monkeypatch.setattr(pipe, "fetch_all", lambda sources: items)
    monkeypatch.setattr(pipe, "summarize_items",
                        lambda top, settings, usage: FeedSummary(sections=[], generated=False))
    s = Settings(feed_enabled=True, data_path=tmp_path, feed_top_n=3, feed_min_per_type=1)
    result = pipe.run_feed_pipeline(tmp_path, s)
    assert "4 fetched" in result
    # store persisted
    from secondbrain.stores.feed import FeedStore
    store = FeedStore(tmp_path / s.feed_db_name)
    assert len(store.get_recent()) == 4
```

- [ ] **Step 3: Run — expect pass**

Run: `uv run python -m pytest tests/unit/feed/test_pipeline.py -v`
Expected: 2 passed.

- [ ] **Step 4: Wire into daily_sync.py** — add `"feed"` to `choices` (line 133) so it reads:

```python
        choices=["inbox", "tasks", "projects", "index", "extract", "weekly", "feed", "all"],
```

Then insert this block immediately after the usage-prune `try/except` (after line 186, before the `try:` at 188 — put it as the first step inside that `try:`):

```python
        if args.command in ("feed", "all"):
            logger.info("--- Refreshing feed ---")
            step_start = time.time()
            from secondbrain.feed.pipeline import run_feed_pipeline

            summary = run_feed_pipeline(vault_path, settings)
            elapsed = int((time.time() - step_start) * 1000)
            logger.info("  %s", summary)
            _log_structured("feed_complete", summary=summary, duration_ms=elapsed)
```

- [ ] **Step 5: Verify daily_sync feed command runs (disabled path, no vault needed beyond flag)**

Run: `uv run python -m secondbrain.scripts.daily_sync feed --vault-path "$SECONDBRAIN_VAULT_PATH" -v 2>&1 | grep -i feed`
Expected: a "Refreshing feed" line and a "Feed disabled" or "Feed: N fetched" summary (depending on `feed_enabled`).

- [ ] **Step 6: Commit**

```bash
git add src/secondbrain/feed/pipeline.py tests/unit/feed/test_pipeline.py src/secondbrain/scripts/daily_sync.py
git commit -m "feat(feed): pipeline orchestrator + daily-sync 'feed' command"
```

---

## Task 7: API endpoints

**Files:**
- Create: `src/secondbrain/api/feed.py`
- Modify: `src/secondbrain/main.py` (register router)
- Modify: `src/secondbrain/models.py` (add `FeedItemResponse`, `FeedSectionResponse`, `FeedResponse`)

- [ ] **Step 1: Add Pydantic models to `models.py`** (near the briefing models)

```python
class FeedItemResponse(BaseModel):
    id: int
    url: str
    source_label: str
    type: str
    title: str
    snippet: str
    summary: str | None
    score: float
    published_at: str | None


class FeedSectionResponse(BaseModel):
    heading: str
    items: list[dict]


class FeedResponse(BaseModel):
    generated: bool
    sections: list[FeedSectionResponse]
    items: list[FeedItemResponse]
```

- [ ] **Step 2: Write `api/feed.py`**

```python
"""Feed API — list ranked items + record clicks. Read path only; refresh is cron-driven."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from secondbrain.api.dependencies import get_settings
from secondbrain.config import Settings
from secondbrain.models import FeedItemResponse, FeedResponse, FeedSectionResponse
from secondbrain.stores.feed import FeedStore

router = APIRouter(prefix="/api/v1", tags=["feed"])


def _store(settings: Settings) -> FeedStore:
    return FeedStore(Path(settings.data_path) / settings.feed_db_name)


@router.get("/feed", response_model=FeedResponse)
async def get_feed(settings: Annotated[Settings, Depends(get_settings)]) -> FeedResponse:
    if not settings.feed_enabled:
        return FeedResponse(generated=False, sections=[], items=[])
    store = _store(settings)
    try:
        rows = store.get_recent(limit=50)
    finally:
        store.close()
    items = [
        FeedItemResponse(
            id=r["id"], url=r["url"], source_label=r["source_label"], type=r["type"],
            title=r["title"], snippet=r["snippet"] or "", summary=r["summary"],
            score=r["score"], published_at=r["published_at"],
        )
        for r in rows
    ]
    # sections built from summarized items grouped by type
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        if r["summary"]:
            by_type.setdefault(r["type"], []).append(
                {"url": r["url"], "title": r["title"], "take": r["summary"]}
            )
    sections = [FeedSectionResponse(heading=t.upper(), items=v) for t, v in by_type.items()]
    return FeedResponse(generated=bool(sections), sections=sections, items=items)


@router.post("/feed/{item_id}/click")
async def record_click(
    item_id: int, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, str]:
    store = _store(settings)
    try:
        url = store.mark_clicked(item_id)
    finally:
        store.close()
    if url is None:
        raise HTTPException(status_code=404, detail="Feed item not found")
    return {"url": url}
```

- [ ] **Step 3: Register the router in `main.py`** — find the block where other routers are `include_router`-ed (e.g. briefing) and add:

```python
from secondbrain.api import feed as feed_routes
...
app.include_router(feed_routes.router)
```

- [ ] **Step 4: Smoke-test the endpoint** (restart API per CLAUDE.md first)

Run: `curl -s http://localhost:8000/api/v1/feed | head -c 200`
Expected: JSON `{"generated":false,"sections":[],"items":[]}` when `feed_enabled=False`, or populated when enabled + pipeline has run.

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/api/feed.py src/secondbrain/models.py src/secondbrain/main.py
git commit -m "feat(feed): GET /feed + POST /feed/{id}/click endpoints"
```

---

## Task 8: Briefing + digest integration

**Files:**
- Modify: `src/secondbrain/models.py` (add `feed_counts` to `BriefingResponse`)
- Modify: `src/secondbrain/api/briefing.py` (`_build_briefing`, `_build_digest`)
- Test: `tests/unit/api/test_feed_digest.py`

- [ ] **Step 1: Add `feed_counts` field to `BriefingResponse`** in `models.py` (default empty so existing callers/tests are unaffected):

```python
    feed_counts: dict[str, int] = {}  # {"ai": 5, "sports": 3} — 0/absent means feed off/empty
```

- [ ] **Step 2: Populate it in `_build_briefing`** — after `today_events` is built (briefing.py ~line 109), before constructing `result`:

```python
    # Feed counts (top items surfaced today), if the feature is on
    feed_counts: dict[str, int] = {}
    if settings.feed_enabled:
        try:
            from secondbrain.stores.feed import FeedStore

            store = FeedStore(Path(settings.data_path) / settings.feed_db_name)
            try:
                for r in store.get_recent(limit=settings.feed_top_n):
                    if r["summary"]:
                        feed_counts[r["type"]] = feed_counts.get(r["type"], 0) + 1
            finally:
                store.close()
        except Exception:
            logger.warning("Feed count lookup failed", exc_info=True)
```

Add `from pathlib import Path` to briefing.py imports. Then pass `feed_counts=feed_counts` into the `BriefingResponse(...)` constructor.

- [ ] **Step 3: Add the feed segment to `_build_digest`** — feed items count toward the notification so the feed is a daily reason to open. Update the count + segments:

```python
def _build_digest(briefing: BriefingResponse) -> DigestResponse:
    overdue = len(briefing.overdue_tasks)
    due = len(briefing.due_today_tasks)
    aging = len(briefing.aging_followups)
    feed_total = sum(briefing.feed_counts.values())
    count = overdue + due + aging + feed_total

    title = f"SecondBrain · {_short_date(briefing.today)}"
    if count == 0:
        return DigestResponse(title=title, body="All clear — nothing needs attention.", count=0)

    segments: list[str] = []
    if overdue:
        segments.append(f"{overdue} overdue")
    if due:
        segments.append(f"{due} due today")
    if aging:
        segments.append(f"{aging} aging follow-up{'s' if aging != 1 else ''}")
    ai = briefing.feed_counts.get("ai", 0)
    sports = briefing.feed_counts.get("sports", 0)
    if ai:
        segments.append(f"{ai} AI update{'s' if ai != 1 else ''}")
    if sports:
        segments.append(f"{sports} sports")

    return DigestResponse(title=title, body=" · ".join(segments), count=count)
```

- [ ] **Step 4: Write digest tests**

`tests/unit/api/test_feed_digest.py`:

```python
from secondbrain.api.briefing import _build_digest
from secondbrain.models import BriefingResponse


def _briefing(**kw):
    base = dict(today="2026-08-04", today_display="Mon", overdue_tasks=[], due_today_tasks=[],
                aging_followups=[], yesterday_context=None, today_context=None,
                today_events=[], total_open=0, feed_counts={})
    base.update(kw)
    return BriefingResponse(**base)


def test_feed_counts_fold_into_digest_body_and_count():
    d = _build_digest(_briefing(feed_counts={"ai": 5, "sports": 3}))
    assert d.count == 8
    assert "5 AI updates" in d.body
    assert "3 sports" in d.body


def test_no_feed_no_tasks_is_all_clear():
    d = _build_digest(_briefing(feed_counts={}))
    assert d.count == 0
    assert "All clear" in d.body


def test_singular_ai_update():
    d = _build_digest(_briefing(feed_counts={"ai": 1}))
    assert "1 AI update" in d.body and "updates" not in d.body
```

- [ ] **Step 5: Run — expect pass**

Run: `uv run python -m pytest tests/unit/api/test_feed_digest.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/secondbrain/models.py src/secondbrain/api/briefing.py tests/unit/api/test_feed_digest.py
git commit -m "feat(feed): fold feed counts into briefing + digest push one-liner"
```

---

## Task 9: Frontend — Feed page + Today block + nav

> Frontend has no test harness here; verification is manual QA (CLAUDE.md rebuild/restart flow). Follow existing patterns in `MorningBriefing.tsx` and page routes under `frontend/src/app/(dashboard)/`.

**Files:**
- Create: `frontend/src/app/(dashboard)/feed/page.tsx`
- Create: `frontend/src/components/briefing/FeedBlock.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx` (toolsNavItems + NAV_COLORS)
- Modify: `frontend/src/components/layout/MobileNav.tsx` (moreItems)
- Modify: `frontend/src/components/briefing/MorningBriefing.tsx` (render `<FeedBlock/>`)

- [ ] **Step 1: FeedBlock.tsx** — fetch `/api/v1/feed`, render sections (AI/Sports) with one-line takes; each item links out and POSTs `/api/v1/feed/{id}/click` on click. Use the existing `fetchJSON()` helper (30s AbortController timeout) and match `MorningBriefing.tsx` card styling. Render nothing when `items` is empty (feature off / no items) so the Today surface stays clean.

- [ ] **Step 2: feed/page.tsx** — full ranked list (`items`) with the daily summary (`sections`) at top; reuse `FeedBlock` for the summary section and a simple list for the remainder. Follow the layout of an existing dashboard page (e.g. `insights/page.tsx`).

- [ ] **Step 3: Sidebar.tsx** — add to `toolsNavItems`: `{ href: "/feed", label: "Feed", icon: Rss }` (import `Rss` from `lucide-react`), and add a `/feed` entry to `NAV_COLORS` matching the existing color pattern.

- [ ] **Step 4: MobileNav.tsx** — add `{ href: "/feed", label: "Feed", icon: Rss }` to `moreItems` (import `Rss`). Per CLAUDE.md, both nav files MUST be updated or the page is unreachable on mobile.

- [ ] **Step 5: MorningBriefing.tsx** — render `<FeedBlock />` in the briefing layout (below tasks/events).

- [ ] **Step 6: Build + restart + QA**

```bash
cd /Users/brentrossin/SecondBrain/frontend && npm run build
launchctl unload ~/Library/LaunchAgents/com.secondbrain.ui.plist
sleep 2 && kill -9 $(lsof -ti:7860) 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.secondbrain.ui.plist
sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:7860/
```
Expected: `200`. Then manually verify: `/feed` reachable on desktop sidebar AND mobile "More"; feed block renders on Home when `feed_enabled=True` and the pipeline has run; clicking an item opens the URL and records the click.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/\(dashboard\)/feed frontend/src/components/briefing/FeedBlock.tsx frontend/src/components/briefing/MorningBriefing.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/components/layout/MobileNav.tsx
git commit -m "feat(feed): Feed page + Today-surface block + desktop/mobile nav"
```

---

## Task 10: Scheduling + docs (WI6)

**Files:**
- Create: `docs/setup/feed-config-example.md` (sample `_config/feed.md`)
- Modify: `CLAUDE.md` (note the `feed` daily-sync command + `feed_enabled` flag)

- [ ] **Step 1: Confirm sequencing.** The existing `com.secondbrain.daily-sync.plist` runs `daily_sync all`, which now includes the `feed` step before inbox — so the feed refreshes well before the 9:15 AM iOS digest pull. No new launchd job needed. Document this.

- [ ] **Step 2: Write `docs/setup/feed-config-example.md`** — a copy-paste `_config/feed.md` with the seed sources/interests as frontmatter, so the user can customize in the vault.

- [ ] **Step 3: Enable + end-to-end QA** — set `SECONDBRAIN_FEED_ENABLED=true` in `.env`, restart API, run `uv run python -m secondbrain.scripts.daily_sync feed --vault-path "$SECONDBRAIN_VAULT_PATH" -v`, then check: `curl -s http://localhost:8000/api/v1/feed | python -m json.tool | head`, and confirm the admin dashboard shows one `feed_summary` usage row with its (tiny) cost.

- [ ] **Step 4: Commit**

```bash
git add docs/setup/feed-config-example.md CLAUDE.md
git commit -m "docs(feed): sample vault config + daily-sync scheduling notes"
```

---

## Final Verification (before tri-review)

- [ ] `uv run python -m pytest tests/unit/feed tests/unit/api/test_feed_digest.py -v` — all green
- [ ] `make check` — lint + typecheck + full test suite clean
- [ ] Feed disabled by default: with `feed_enabled=False`, `/api/v1/feed` returns empty and digest is unaffected
- [ ] Cost visible: one `feed_summary` row per pipeline run in the admin dashboard
- [ ] `/feed` reachable on desktop AND mobile; feed block on Home; click records + opens

---

## Spec Coverage Check

| Spec WI | Task(s) |
|---|---|
| WI1 Source config + interest profile (vault-as-truth) | Task 0 (flags), Task 1 (config reader + seed defaults) |
| WI2 Fetcher + FeedStore | Task 3 (fetch), Task 5 (FeedStore) |
| WI3 Heuristic ranker | Task 2 |
| WI4 Batched daily summary (one LLM call) | Task 4 (+ UsageStore logging) |
| WI5 Feed page + brief block | Task 7 (API), Task 8 (digest), Task 9 (frontend) |
| WI6 Scheduling | Task 6 (daily-sync command), Task 10 (docs/sequencing) |

All six work items covered. Cost controls (single batched call, top-N, no embeddings, 30-day prune, UsageStore logging) are implemented in Tasks 4/5/6.
