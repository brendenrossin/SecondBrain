---
spec: 006-feed-engagement-learning-and-save-to-vault.md
spec_version: 0.1.0
reviewer: architect
round: 1
verdict: approve with changes
date: '2026-11-22'
---
## Architect review — 006
Verdict: approve with changes

- [x] **BLOCKER** Saving the same item twice overwrites the vault page and pays for the LLM calls again. Decision 4 says "KLIB-1's own duplicate-page check covers saving the same thing twice", but the code doesn't work that way. `IngestionPipeline.run` (`/Users/brentrossin/code/second-brain/src/secondbrain/ingestion/pipeline.py:72-106`) runs fetch, then the Sonnet audit, then `find_existing_by_source`, then the Haiku compile, and then **overwrites** the page it found. — A double-tap on mobile or a later re-save pays a second Sonnet audit and Haiku compile. It also silently replaces a `Wiki/` page you may have edited since. That breaks the Intent ("without ever editing my notes"). — Fix: have `POST /feed/{id}/save` short-circuit when `feed_items.saved_at IS NOT NULL`, returning 409 or the prior state without starting a job. The frontend should disable the save control once `saved` is true. Add a scenario for this, and correct the text of Decision 4. — resolved: v0.2.0 Decision 4. feed_saves claim → 409 'already saved to <path>' / 'save already in progress'. The UI disables save once saved. Two scenarios added.

- [ ] **SHOULD** The save flow's order and threading are not specified, and the `mark_saved` interface contradicts an acceptance criterion. As sketched, `mark_saved(item_id, keywords) -> url` stamps `saved_at` and returns the URL in a single call. But the "URL the pipeline rejects" scenario needs `saved_at` to stay NULL after `detect_content_type` fails, which means the lookup has to happen before the stamp. Also, `_start_ingestion_job` (`/Users/brentrossin/code/second-brain/src/secondbrain/api/wiki.py:98-140`) calls `asyncio.create_task`, so it must run on the event-loop thread and not inside the `asyncio.to_thread` helper every feed endpoint uses. — Fix: spell out the sequence:
  1. `to_thread(get_item)`, giving 404 if missing.
  2. `detect_content_type`, giving 422.
  3. `_start_ingestion_job(url)` on the loop.
  4. `to_thread(mark_saved)`.

  Split the interface into a read (`get_item`) and a stamp (`mark_saved -> bool`). State that a failed stamp after the job has started is logged, not a 500, because the job is already running.

- [ ] **SHOULD** The spec doesn't say where vote-time keywords come from. `set_vote`, `record_click_signal` and `mark_saved` all take `keywords`, and `matched_keywords` needs `interests`. So the API process would have to call `load_feed_config` against the vault on every vote and click. That function never raises and quietly returns `SEED_DEFAULTS` when the note is missing or unreadable (`/Users/brentrossin/code/second-brain/src/secondbrain/feed/config.py:108-118`), so wrong keywords could be snapshotted with no error. — Fix (simplest): take the keywords from the item's stored `rank_why` (the config keywords it actually matched at rank time) inside the store method, so callers pass nothing. Fall back to `()` for rows ranked before the migration. `GET /feed/learning` does need `interests` for `compute_adjustments`, so state that it reads the vault config. Note it in the "Explain" scenarios.

- [ ] **SHOULD** The migration's rollback promise doesn't match how `sqlite3` works, and a partial migration would stop refreshes. With Python's default (legacy) isolation level, `ALTER TABLE`/`CREATE TABLE` run in autocommit, so `rollback()` won't undo a column that was already added. The "user_version stays 1, transaction rolled back" scenario will only pass if the code issues an explicit `BEGIN`. Separately, the existing `_migrate` returns early on `version >= 1` and runs the v1 backfill unconditionally, so it has to become per-version steps. Worst case: if v2 fails, `add_items` (now writing `rank_why`) raises on every hourly run, and `daily_sync feed` swallows the error. The feed then stops updating with only a warning. — Fix:
  - Move `CREATE TABLE IF NOT EXISTS feed_signals` and its index into the idempotent `_init_schema` script.
  - Add the columns with `PRAGMA table_info` guards inside an explicit `BEGIN … COMMIT`.
  - Gate each step on `version < N`.
  - Either make the `rank_why` write tolerate a missing column, or state that a failed migration is retried on every open (which the guards make safe).

- [ ] **SHOULD** `FeedLink` wraps its whole row in an `<a>` (`/Users/brentrossin/code/second-brain/frontend/src/components/feed/FeedBlock.tsx:62-88`). Putting vote and save buttons inside it is invalid HTML (interactive content inside an anchor), and `preventDefault`/`stopPropagation` workarounds are unreliable on mobile Safari. — Fix: restructure the row so the anchor holds only the title, take and meta, with the controls as a sibling. Note that the controls must not render when `id` is undefined. `FeedBlock` passes `stored?.id`, which can be undefined.

- [ ] **SHOULD** The click path is two calls, but "first click" requires reading and writing in one transaction. `mark_clicked` currently overwrites `clicked_at` unconditionally (`/Users/brentrossin/code/second-brain/src/secondbrain/stores/feed.py:272-282`), so a separate `record_click_signal` call afterwards can no longer tell whether this was the first click. — Fix: fold it into `mark_clicked`. In one transaction, read `clicked_at` and `vote`, set `clicked_at = COALESCE(clicked_at, now)`, and insert the click signal with `INSERT … ON CONFLICT(item_url) DO NOTHING` only when this is the first click and there is no vote. Drop `record_click_signal` from the interface.

- [ ] **NIT** Decision 4 describes the flow as "→ `Wiki/` → index", but `_start_ingestion_job` passes no `index_callback`. A saved page is not indexed until the next reindex. Correct the text so the Saved state doesn't promise it is searchable.

- [ ] **NIT** `add_items` uses `ON CONFLICT(url) DO UPDATE` with an explicit column list. `rank_why` must be added to both the INSERT and the update set, or re-ranked items keep yesterday's breakdown. Worth one line in the Files note for `stores/feed.py`.

- [ ] **NIT** `GET /feed/learning` returns `signals` counts per source, but `LearnedAdjustments` carries only multipliers. Either add the counts to the dataclass or say the endpoint counts them itself.

- [ ] **NIT** Sending `none` deletes the item's only signal, so an item that was clicked, then voted, then cleared loses its click history. That may be intended. If so, say so in Decision 5.

Decisions worth an ADR: ADR-012 (already cited). It covers learned state living in `feed.db` as an event log, not in the vault, plus reset-by-delete. That is the one expensive-to-reverse choice here. Nothing else needs a new ADR.

Files reviewed: `/Users/brentrossin/code/second-brain/docs/specs/006-feed-engagement-learning-and-save-to-vault.md`, `/Users/brentrossin/code/second-brain/src/secondbrain/feed/rank.py`, `/Users/brentrossin/code/second-brain/src/secondbrain/feed/pipeline.py`, `/Users/brentrossin/code/second-brain/src/secondbrain/feed/models.py`, `/Users/brentrossin/code/second-brain/src/secondbrain/feed/config.py`, `/Users/brentrossin/code/second-brain/src/secondbrain/stores/feed.py`, `/Users/brentrossin/code/second-brain/src/secondbrain/api/feed.py`, `/Users/brentrossin/code/second-brain/src/secondbrain/api/wiki.py`, `/Users/brentrossin/code/second-brain/src/secondbrain/ingestion/pipeline.py`, `/Users/brentrossin/code/second-brain/src/secondbrain/ingestion/fetcher.py`, `/Users/brentrossin/code/second-brain/frontend/src/components/feed/FeedBlock.tsx`, `/Users/brentrossin/code/second-brain/frontend/src/lib/api.ts`. The `sendBeacon` change is fine: `BASE` is the same-origin `/api/v1`, so cross-origin and CORS rules don't come into it.
