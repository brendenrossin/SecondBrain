# Feature: FEED-1 — RSS Attention Router

**Date:** 2026-09-05
**Branch:** `feed-1-attention-router` → merged as [#13](https://github.com/brendenrossin/SecondBrain/pull/13) (squash `1bb26c1`)

## Summary

A daily feed of AI and sports news on the same Today surface as tasks and notes.
Free heuristic filtering picks the day's ~10 best items out of ~150 fetched, then
**exactly one** batched Haiku call writes a one-line take per item plus a
per-section overview. Sources and interest weights live in the vault
(`_config/feed.md`), not in code. Measured cost: **~$0.10/month**.

## Problem / Motivation

The system was entirely inward-facing — it could answer questions about notes
already written. The retention thesis (see ROADMAP "ENGAGE + FEED share one push
surface") is that a daily habit needs a reason to open the app on a day when you
have nothing to ask it. That means bringing the *outside world* onto the surface
ENGAGE-1 already built.

The hard constraint was cost. A naive "summarize my feed" implementation makes one
LLM call per article per day — at ~150 articles that is roughly $4–6/month for a
personal reader, and it scales with the number of sources, which is exactly the
wrong direction. The design had to make adding a source approximately free.

## Solution

**Filter before you spend.** The pipeline is `config → fetch → dedup → rank →
persist → summarize → prune`, and every step before `summarize` is pure
arithmetic:

```
score = trust × (1 + Σ matched interest weights) × recency_decay
```

with `recency_decay` on a 48-hour half-life. No embeddings, no model, no network
beyond the RSS fetch itself. Only the top-N survivors reach the single batched
LLM call, so cost is a function of `feed_top_n` (10) — **not** of how many sources
are subscribed.

**The vault stays the source of truth.** Sources and interest keywords are parsed
from a Markdown note. Feed rows are transient derived data with a 30-day prune;
nothing about the feed is application state the user cannot see and edit.

**Failure is never fatal.** The `daily_sync feed` step runs *last* and swallows its
own exceptions, so a dead feed, a network partition, or an LLM outage can never
abort the core vault sync.

## Files Modified

**Feed module (new)** — `src/secondbrain/feed/`
- `config.py` — parses `_config/feed.md`; field-level coercion so one bad value
  degrades that field, never the whole config
- `fetch.py` — bounded HTTP via `httpx`, feedparser used as a *parser only*
- `text.py` — `strip_html`, shared by fetch and the store's backfill
- `rank.py` — dedup, scoring, top-N selection with a per-type floor
- `summarize.py` — the single Haiku call; prompt construction and JSON parsing
- `pipeline.py` — orchestration + the refresh interval guard
- `models.py` — dataclasses (transient, not vault content)

**Storage / API / UI**
- `stores/feed.py` — SQLite (WAL), upsert on URL, `feed_section_overviews`,
  a `PRAGMA user_version` migration
- `api/feed.py` — `GET /api/v1/feed`, `POST /api/v1/feed/{id}/click`
- `api/briefing.py` — windowed feed counts folded into the digest
- `scripts/daily_sync.py` — the `feed` step
- `frontend/` — `feed/page.tsx`, `components/feed/FeedBlock.tsx`, `lib/api.ts`,
  `lib/types.ts`, `lib/utils.ts` (`timeAgo`), `Sidebar.tsx`, `MobileNav.tsx`
- `docs/setup/feed-config-example.md` — copy-paste vault config

## Key Decisions & Trade-offs

**Withhold URLs from the prompt; reattach by index.** The first design asked the
model to echo each item's URL back so takes could be matched. Live, **2 of 10
items came back with a URL lifted from inside the article snippet** — and it hit
the two top-ranked AI stories, silently dropping their takes. Items are now
numbered and the model refers to `{"i": 1}`. Indexes cannot be mistranscribed,
they halve the output tokens, and — the real win — **no model-authored text ever
becomes an `href`**.

**Strip HTML at ingestion, before truncating.** RSS `summary` is HTML. Storing it
verbatim broke three things at once: the UI printed literal `<p><strong>` at the
reader, the prompt paid tokens for markup, and the 400-char cap spent its budget
on tags. This was also the *root cause* of the URL-substitution bug above — the
model was copying `href`s it could see in the snippets. Fixing it cut input
tokens 1010 → 859 and the monthly cost $0.16 → $0.10.

`strip_html` uses an **allowlist of real HTML element names**, not `<[^>]*>`. The
permissive pattern destroys prose: `"Why x<y matters > 3"` → `"Why x 3"`. It also
re-strips *after* entity decoding, because `convert_charrefs` decodes `&lt;script&gt;`
into live markup only after tags have been removed. The function is idempotent,
which the store's backfill depends on.

**Only type-pure sections get an overview.** The model authors section headings as
free text ("Sports", "AI news", "AI/ML"), while the read path groups by our own
`type` column. Joining on the *items'* types avoids depending on the model
spelling a heading consistently. A section spanning types means the model ignored
the grouping instruction — filing it under the majority type would print a sports
paragraph under the AI header, and **a confidently wrong read is worse than an
absent one**, so mixed sections are skipped.

**Upsert, don't ignore, on re-fetch.** `INSERT OR IGNORE` froze each item's score
at first insert. With a 48-hour recency half-life that let day-one items outrank
fresh ones for the entire 30-day retention window. Engagement columns (`shown_at`,
`clicked_at`) and the LLM summary are deliberately preserved across the upsert.

**A refresh interval guard, not a schedule change.** The deployed daily-sync job
runs *hourly* and `all` includes the feed step — 24 LLM calls/day, ~24× budget.
Fixed with `feed_min_interval_hours` inside the pipeline rather than by removing
`feed` from `all`, so the protection survives someone re-adding it.

**No snippets in the leftovers list.** The unsummarized remainder is a *scanning*
surface; 40-odd previews buried the summarized section that actually earned the
LLM call. Headline + source + age only, grouped by type, capped at 8 per group.

## Patterns Established

- **Cost-shaped pipelines.** Order steps so everything free happens before
  anything paid, and make the paid step's cost depend on a config constant rather
  than on input volume.
- **`PRAGMA user_version` for one-time data fixes** in the SQLite stores — the
  migration runs once per database and travels with a copied file.
- **Migrations must not use the store's `_run` retry helpers.** `_run`'s reconnect
  re-enters the `conn` property, which calls `_init_schema` → `_migrate` → `_run`:
  unbounded recursion. Migration code calls `self.conn` directly, with a comment
  saying why.
- **Model output is data, never identity.** Resolve model responses against our
  own records by index or key; never let generated text become a URL, a CSS class,
  or a database key.
- **Two layers for link safety** — scheme check at ingestion, `new URL()` protocol
  allowlist at render.

## Testing

**899 tests at merge** (up from 756 on main before the branch), covering: config
coercion, HTML stripping including hostile and entity-encoded input, ranking and
recency math, dedup scoping, prompt construction, JSON parsing and fallback,
store upsert/migration/overview semantics, API shape and flag gating, and digest
integration.

Two test classes are worth knowing about:
- `TestBackfillFailureSafety` — verified by *removing* the `rollback()` and
  watching both tests go red.
- `TestStripHtmlHostileInput` — pins the idempotence and no-live-markup contracts
  that the backfill depends on.

**Verified live**, not just in tests: a real refresh (138–158 items, `generated=True`),
overviews attaching under the stricter type-purity rule, `$0.0034/run` in the usage
store, the interval guard returning `Feed skipped` and spending nothing, and both
UI surfaces rendered in a browser.

## Future Considerations

- **FEED-2 (engagement learning)** is the natural next step; `shown_at`/`clicked_at`
  are already recorded and `POST /feed/{id}/click` already writes them.
- **Overview text is model-authored and unmarked as generated.** A hostile feed
  entry can steer it. Ceiling today is text-only spoofing in the user's own reader
  (URLs are never model-controlled), and it is capped at 400 chars — but this needs
  revisiting when FEED-2 pushes that text to a phone notification or writes it into
  a vault note, where escaping guarantees differ. Flagged in the backlog.
- **On an LLM-failure day** the top block shows headlines plus each item's snippet
  under a "headlines only" badge. Acceptable, but the fallback has never run against
  a real outage.
- **No frontend test runner exists**, so `timeAgo`, `sourceMeta`, `groupByType` and
  the show-more toggle have no automated coverage.
- Remaining deferred items are recorded in
  `docs/optimizations/feed-1-attention-router-backlog.md`.
