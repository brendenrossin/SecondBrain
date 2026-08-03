# FEED-1 — Personalized Attention Router (RSS Trial)

> **Status:** Pending
> **Estimated effort:** 2-3 days
> **Depends on:** ENGAGE-1 (Today surface + daily push plumbing)
> **Priority:** High — the thing the user explicitly misses (staying on top of AI + interests)

## Problem

The user stopped keeping up with the AI space (podcasts, newsletters, Twitter) and juggles six apps for AI + sports news. They want one personalized daily brief — "here's what's going on" across their interests — pushed to them, that learns from what they engage with. The hard constraint is **cost**: no summarizing everything, no embedding everything, no storing content that won't be read. Trial cheap, expand only if the habit sticks.

## Solution

A **filter-before-you-spend** pipeline. Ingest headlines for free (RSS), rank with free heuristics, and spend LLM tokens on **only the top N items, in a single batched call per day**. Feed items are transient derived data (SQLite, pruned) — not vault content. Only items the user explicitly saves become vault notes (FEED-2, via the existing KLIB-1 ingestion pipeline).

**Cost target: ~$0.15/month.** RSS + ranking are free; one Haiku summary call/day is ~$0.005/day; no embeddings; 30-day pruning.

### Cost architecture (the whole point)

| Stage | Cost | How |
|-------|------|-----|
| Ingest | Free | `feedparser` over RSS — titles + snippets only |
| Dedup | Free | URL + normalized-title match; local BGE only if needed later |
| Rank | Free | Heuristic: source trust × interest-keyword match × recency |
| Summarize | ~$0.005/day | **One** batched `claude-haiku-4-5` call over the top ~10 items |
| Store | Negligible | SQLite rows (no content bodies beyond snippet); prune >30d |
| Track | — | Log the one call to `UsageStore` so cost is visible in the admin dashboard |

### WI1: Source config + interest profile (vault-as-truth)

**Goal:** User-editable sources and interests; no source code edits.

**Behavior:**
- A vault config note (e.g. `_config/feed.md`) with frontmatter listing: `sources` (RSS url, label, `type` ∈ {ai, sports, general}, `trust` weight 0–1) and `interests` (keyword → weight). Mirrors the configurable-categories pattern (config lives in the vault).
- Seed defaults: **AI** — a handful of free-RSS sources (Anthropic/Simon Willison/Latent Space/Nate B Jones-style newsletters; verify RSS availability per source during implementation). **Sports** — ESPN + team feeds for Padres, Michigan football, NFL.
- Missing/malformed config → fall back to built-in seed defaults, never crash.

**Files:** `src/secondbrain/scripts/` (config loader), `src/secondbrain/config.py` (path setting + feature flag `feed_enabled: bool = False`).

### WI2: Fetcher + FeedStore

**Goal:** Poll sources, dedup, persist transient items.

**Behavior:**
- `feedparser`-based fetch of each source (timeout per source; one dead feed never blocks the batch — mirror the per-block defensiveness from ENGAGE-1).
- `FeedStore` (SQLite, mirrors `stores/usage.py`: WAL, busy_timeout, reconnect-on-error). Columns: `id`, `url`, `source_label`, `type`, `title`, `snippet`, `published_at`, `fetched_at`, `score`, `summary` (nullable), `shown_at`, `clicked_at`.
- Dedup on normalized URL + title before insert (`INSERT OR IGNORE`). No content bodies stored beyond the RSS snippet.
- `prune_old(days=30)` — mirror `prune_old_usage`.

**Files:** `src/secondbrain/stores/feed.py` (new), `src/secondbrain/scripts/feed_fetch.py` (new).

### WI3: Heuristic ranker (no LLM)

**Goal:** Rank fetched items using only free signals.

**Behavior:**
- `score = source_trust × interest_match × recency_decay`, where `interest_match` sums interest-keyword weights hit in title+snippet, and `recency_decay` favors last 24–48h.
- Deterministic and transparent (the user can see *why* an item ranked). This is also the surface FEED-2's engagement learning will tune (click → nudge interest/source weights).

**Files:** `src/secondbrain/scripts/feed_rank.py` (new) or a ranker module.

### WI4: Batched daily summary (the one LLM call)

**Goal:** Turn the top-ranked items into a readable brief in a single call.

**Behavior:**
- Take top ~10 items across types (guarantee a minimum for each of AI / sports so one domain can't crowd out the other), send **one** `claude-haiku-4-5` call: input = titles + snippets + source labels; output = a grouped brief (AI section, sports section) with one-line takes and links.
- Structured output (grouped sections) so the frontend renders cleanly and unknown items degrade gracefully.
- Write the summary back onto the item rows; log the call to `UsageStore` (provider/model/tokens via existing `calculate_cost`) so the trial's real cost shows in the admin dashboard.
- 60s timeout on the LLM client (project standard). If the call fails, fall back to showing the ranked headlines *without* summaries — the feed still works, just unsummarized.

**Files:** `src/secondbrain/scripts/feed_summarize.py` (new; reuse the `anthropic` client pattern from `ingestion/compiler.py`).

### WI5: Feed page + brief block

**Goal:** Surface the feed in the app and on the Today surface.

**Behavior:**
- A `feed` briefing block (plugs into ENGAGE-1's block registry) — top few items grouped by section, on the Today surface. Clicking an item records `clicked_at` (the signal FEED-2 learns from) and opens the source URL.
- A dedicated `/feed` page (nav: desktop `Sidebar.tsx` Tools + mobile `MobileNav.tsx` More — **update both**) showing the full ranked list with the daily summary at top.
- The daily push one-liner (ENGAGE-1 WI3) includes a feed count: e.g. "5 AI updates · 3 Padres."

**Files:** `frontend/src/app/(dashboard)/feed/` (new page), `frontend/src/components/briefing/blocks/FeedBlock.tsx` (new), `Sidebar.tsx` + `MobileNav.tsx`, `src/secondbrain/api/` (new `feed.py` endpoints: get feed, record click).

### WI6: Scheduling

**Goal:** Refresh once a day, before the push fires.

**Behavior:**
- fetch → rank → summarize → prune runs from the daily-sync cron (or a new `com.secondbrain.feed.plist`) sequenced **before** the ENGAGE-1 daily push so the push reflects fresh items.
- ChromaDB single-process rule doesn't apply (no vectors here), but respect the same trigger/sequencing discipline as daily-sync.

## Implementation Order

WI1 → WI2 → WI3 → WI4 (backend pipeline, testable via script) → WI5 (frontend) → WI6 (schedule). Ships behind `feed_enabled` flag so it can be trialed without affecting anyone cloning the repo.

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| Engagement learning (click → weight tuning) | FEED-2 |
| Save-to-vault via KLIB-1 | FEED-2 |
| Google Calendar | FEED-3 |
| Gmail / newsletter ingestion | FEED-4 |
| X/Twitter, podcast transcription | FEED-5 — expensive, deferred |
| Embeddings / semantic dedup | Not needed for a daily ranked list; local BGE only if dedup proves insufficient |
| Full-article fetch/summary | Snippet-only keeps cost near zero; full fetch is a save-to-vault (KLIB-1) action |

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cost creep (summarizing too much) | High (user's #1 concern) | Single batched call, top-N only, no embeddings; cost logged to UsageStore + visible in admin |
| A source lacks RSS / feed dies | Medium | Per-source timeout; skip dead feeds; seed-default fallback |
| One domain crowds out the other | Low | Per-type minimums in the top-N selection |
| Summary call fails | Low | Fall back to unsummarized ranked headlines |
| Repetitive items kill the "fresh" payoff | Medium | Dedup on URL+title; don't re-show items already `shown_at` |

## Testing

**Automated:**
- Ranker is deterministic: same items + profile → same order; keyword weighting behaves
- Dedup: same URL/title inserted twice → one row
- `prune_old(30)` removes only stale rows
- Summarizer failure → falls back to headlines without throwing
- Per-type minimum enforced in top-N selection

**Manual QA:**
- Run `feed_fetch` → `feed_rank` → `feed_summarize` manually; inspect FeedStore rows and one brief
- Feed block appears on Today surface; `/feed` page reachable on desktop **and** mobile
- Click an item → `clicked_at` recorded, URL opens
- Check admin dashboard: the daily summary call shows its real (tiny) cost

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Filter with heuristics before any LLM | The entire cost strategy; free signals decide what's worth a token |
| One batched summary call/day | ~$0.005/day vs. per-item summarization = pennies vs. dollars |
| No embeddings in the trial | A daily ranked list isn't a searchable corpus; local BGE later if dedup needs it |
| Feed items are transient (SQLite, pruned) | Only user-saved items become vault content (FEED-2) — keeps the vault clean and storage tiny |
| Config + interests live in the vault | Vault-as-truth; user edits sources/interests without touching code |
| Ship behind `feed_enabled` flag | Trial without affecting repo cloners; easy on/off |
| Log the summary call to UsageStore | Makes the trial's real cost visible — proves the cheapness claim |
| Defer X/podcasts to FEED-5 | X API ~$200/mo, Whisper expensive; earn them only if the cheap feed proves the habit |
