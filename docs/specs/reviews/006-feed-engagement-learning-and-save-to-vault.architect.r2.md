---
spec: 006-feed-engagement-learning-and-save-to-vault.md
spec_version: 0.2.0
reviewer: architect
round: 2
verdict: approve with changes
date: '2026-11-22'
---
## Architect review — 006
Verdict: approve with changes

I traced the save flow from end to end: `api/feed.py` to `wiki._start_ingestion_job` to `IngestionPipeline.run` to the merge in `_run`. I also traced the rank flow: `rank_items` to `add_items` to `update_summaries`, and `summarize` does not touch `score`, so the rank_why/score property holds. Finally I traced the read path: `_fetch_recent` to `get_recent` to `_to_item` to `FeedBlock` / `feed/page.tsx`. The design fits the existing code: a per-request `FeedStore`, WAL + busy_timeout, and the in-memory `_jobs` tracker. Nothing blocks it. The items below would change what gets built.

- [ ] **SHOULD** `wiki_path` is stored as an absolute filesystem path. `IngestionPipeline.run` sets `job.result_path = str(dest)`, where `dest` is under `settings.vault_path / "Wiki"` (`ingestion/pipeline.py:115`). The AC assumes `"Wiki/x.md"`. As written, `complete_save` would put `/Users/.../vault/Wiki/x.md` into `feed_saves`, into `GET /feed` (which is served over Tailscale to the phone), and into the 409 detail. Suggested fix: in `on_complete`, store `Path(job.result_path).relative_to(settings.vault_path)` (falling back to the name), and add that to Decision 4 and the AC.
- [ ] **SHOULD** Decision 4 step 5 leaves undefined what happens if `record_signal(..., "save")` fails after the job has already started. Returning 500 tells the UI the save failed while KLIB-1 is in fact running. A retry would then get "save already in progress" for up to 15 minutes. Suggested fix: once the job has started, log a failed save-signal write and still return the `WikiIngestResponse`. The `feed_saves` row is the authoritative intent record. Add a scenario for this.
- [ ] **SHOULD** Decision 6 has two problems with per-version migration bookkeeping.
  - It does not say to bump `user_version` after each step. On a v0 db where the backfill succeeds and the ALTER fails, the version has to end at 1, or the next open strips the same rows again. The existing `_migrate` docstring exists to prevent exactly that.
  - "A rollback is not something to rely on" must not turn into deleting the existing `rollback()`. The v1 step is DML in an implicit transaction, and the current code rolls it back so a failed pass doesn't keep holding the write lock the cron then blocks on (`stores/feed.py:124-131`).

  Suggested fix: write it as a commit plus `PRAGMA user_version = N` per step, keep the rollback in the except, and add a "v0, backfill ok, ALTER fails, so version is 1" scenario.
- [ ] **SHOULD** `frontend/src/app/(dashboard)/feed/page.tsx` is missing from Files. `RestGroup` renders `FeedLink` and passes each prop explicitly (`id`, `url`, `title`, `source`, `publishedAt`). The new `vote` / `save_state` / `wiki_path` / `why` props won't reach the "More from your sources" rows, which hold most of the 968 items, unless that file changes. Suggested fix: add page.tsx to Files. Alternatively, change `FeedLink` to take the `FeedItem` (plus an optional take override) so both call sites get the new fields without listing them again. Also say whether the controls should appear in `MorningBriefing`'s `FeedBlock`: they will by default, because it is the same component.
- [ ] **SHOULD** `api/feed.py` would import and patch a private function from another router (`secondbrain.api.feed._start_ingestion_job`). With `on_complete`, that function becomes a contract two routers depend on. Suggested fix: rename it to `start_ingestion_job` (keep the leading-underscore name as an alias if that's easier) and have `feed.py` import it as a module attribute so the patch target stays stable. It does not need to move into a service layer. That would be speculative.
- [ ] **NIT** The completion callbacks are keyed only by URL. Suppose a stale claim is retaken at 15 minutes while the first job is still running. The first job's `on_complete` would then `fail_save` or `complete_save` over the second claim, and a `fail_save` would release the claim while job 2 is still running. The likelihood is low because the LLM timeouts are 60s. If you want to close it, guard `complete_save` / `fail_save` with `WHERE requested_at = <the claim's requested_at>`.
- [ ] **NIT** `SaveClaim` is used in the Interfaces but never defined. Define it as a dataclass with `ok`, `reason` and `wiki_path`.
- [ ] **NIT** `api.ts` has no `getIngestStatus`. The existing function is `wikiIngestStatus` (`frontend/src/lib/api.ts:359`).
- [ ] **NIT** Decision 3 says "a single upsert or delete statement" per operation. But `set_vote` and `mark_clicked` need a read of `source_label`/`rank_why` first, and `mark_clicked` writes twice. Reword it as "one `with self.conn:` transaction, no `_run` retry" so the builder doesn't go looking for a single-statement form.
- [ ] **NIT** "The endpoint accepts any body and any content type" already holds for the click endpoint: it declares no body parameter. Only the test needs adding, not a code change.
- [ ] **NIT** The new vote and save endpoints don't check `settings.feed_enabled`. Save spends Anthropic money. Consider returning 404 when the feed is disabled, so these endpoints match `GET /feed`.
- [ ] **NIT** In `run_feed_pipeline`, put `prune_signals(180)` after `prune_old`, inside the same try. Then a failed signal prune can't skip `mark_shown` or the item prune.

Decisions worth an ADR:
- Decision 1: user-intent state (votes, save lifecycle) lives in `feed.db` as a named exception to "the vault is the single source of truth". ADR-012 covers only the slice-2 weights. This slice is where the exception is first created, and undoing it later means migrating user data.
- The `rank_why` JSON shape persisted in `feed_items`. Slice 2 will extend it and the UI depends on it, so it becomes a stored contract.

Relevant files:
- /Users/brentrossin/code/second-brain/docs/specs/006-feed-engagement-learning-and-save-to-vault.md
- /Users/brentrossin/code/second-brain/src/secondbrain/stores/feed.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/feed.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/wiki.py
- /Users/brentrossin/code/second-brain/src/secondbrain/ingestion/pipeline.py
- /Users/brentrossin/code/second-brain/src/secondbrain/feed/rank.py
- /Users/brentrossin/code/second-brain/src/secondbrain/feed/pipeline.py
- /Users/brentrossin/code/second-brain/frontend/src/components/feed/FeedBlock.tsx
- /Users/brentrossin/code/second-brain/frontend/src/app/(dashboard)/feed/page.tsx
- /Users/brentrossin/code/second-brain/frontend/src/lib/api.ts
