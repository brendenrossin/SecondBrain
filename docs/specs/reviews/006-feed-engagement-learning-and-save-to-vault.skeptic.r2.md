---
spec: 006-feed-engagement-learning-and-save-to-vault.md
spec_version: 0.2.0
reviewer: skeptic
round: 2
verdict: approve with changes
date: '2026-11-22'
---
## Skeptic review — 006 (v0.2.0, round 2)
Verdict: approve with changes

The rescope fixed the round-1 blockers. Keywords now come from rank_why, the save flow is ordered with a claim, "saved" means the job completed, and the degraded modes are written down. Everything left is a gap a builder would fill by guessing. None of it needs a redesign.

Unstated assumptions:
1. `job.result_path` is a vault-relative path like `Wiki/x.md`. It is not: `IngestionPipeline.run` sets `result_path = str(dest)`, and `dest` is `settings.vault_path / "Wiki" / …`, an absolute path (`ingestion/pipeline.py:115`, `api/wiki.py:107`). The ACs expect `"Wiki/x.md"` in `wiki_path` and in the 409 detail. — Not written down.
2. `on_complete` runs on both ways a job can end. In `_run` (`api/wiki.py:124-135`) a job can fail through the pipeline's returned status or through the `except` branch. The spec only says it runs "after the result is merged". — Not written down.
3. Once a URL is saved, the page stays in the vault. If I delete or move the Wiki page in Obsidian, `feed_saves` still says "saved", is never pruned, and every retry gets 409 "already saved to <path>". — Not written down. This also cuts against "vault is the source of truth".
4. Which rows get the controls. `FeedLink` is used in three places: the Today-surface `FeedBlock`, the summarized sections on `/feed`, and the `RestGroup` rows (`feed/page.tsx:30-69`). The `RestGroup` comment says those rows are deliberately minimal, a "scanning surface" of 40-odd rows. Changing `FeedLink` puts four controls on every one of them. — Not written down.
5. Running the v1 backfill twice is harmless. It is not: `strip_html` unescapes, so `&lt;b&gt;` becomes `<b>` on the first pass and is stripped on the second. — Not written down. It matters for the 0→2 path (see the migration SHOULD).
6. The click POST is being dropped today. The links use `target="_blank"`, which doesn't unload the page, so a plain `fetch` normally completes. The spec's own evidence says clicks are low because I read in place, not because requests are lost. — Not written down. Goal 4 has no evidence behind it.
7. After a page reload a pending save can still be followed. `feed_saves` doesn't store the `job_id`, and `_jobs` lives in process memory and is capped at 100. A reloaded page sees `save_state: "pending"` with nothing to poll. — Not written down.

- [ ] **SHOULD** `wiki_path` is absolute in reality but relative in the ACs. — A builder either stores `/Users/.../vault/Wiki/x.md` (which shows up in the UI and the 409 detail and fails the AC) or quietly relativizes it. — Say that `complete_save` stores `Path(job.result_path).relative_to(settings.vault_path)` (posix), and add that case to the "counts as saved" AC.
- [ ] **SHOULD** It is not defined which way a job has to end for `on_complete` to run. — If it only runs after the success merge, an exception inside `pipeline.run` or `to_thread` leaves the claim pending for 15 minutes with `save_state: "pending"`. The "failed job can be retried" AC wouldn't catch this, because it only covers a returned FAILED status. — Say that `on_complete` runs in a `finally` after the status is final, covering both the merge and the `except` path. Add an AC where the pipeline raises.
- [ ] **SHOULD** Step 5 (`record_signal(..., "save")`) can fail after the job has started. — The endpoint would return 500 while KLIB-1 is running and spending, the UI would show an error, and a retry would get 409 "in progress". — Decide which you want: a signal-write failure is logged and the endpoint still returns the `WikiIngestResponse`, or the signal is written before the job starts and removed if the start fails. Add one AC.
- [ ] **SHOULD** The saved state can outlive the vault page (assumption 3). — The no-double-save guard becomes a no-save-ever guard for a page I deleted on purpose. — In `claim_save`, treat a "saved" row whose `vault_path / wiki_path` no longer exists as claimable. The path check is cheap. Add an AC.
- [ ] **SHOULD** Migration step bookkeeping is ambiguous for 0→2. Decision 6 says "a failure … leaves `user_version` at its old value". — Starting from v0, if the backfill succeeds and the v2 ALTER fails, the version stays at 0 and the next open re-runs a backfill that isn't idempotent (assumption 5). — Bump `user_version` after each step (0→1 commits with the backfill, as today), and say so. Add a variant of the failure AC that starts from v0 and asserts the version ends at 1.
- [ ] **SHOULD** Where the controls render is unspecified (assumption 4). — One engineer puts 👍👎💾 and why on all ~50 rows and on the Today briefing, another only on summarized items. That changes the day-28 denominator and the page density. — Name the surfaces (summarized sections on `/feed` and Today? `RestGroup` too?). If rest rows get controls, say the `RestGroup` "deliberately minimal" rationale is being overridden on purpose.
- [ ] **SHOULD** A reloaded pending save has nothing to poll (assumption 7). — "After a reload, that state comes from `save_state`" leaves "Saving…" frozen until the next full reload. — Either store `job_id` in `feed_saves` and let the UI resume polling (and fall back to `/feed` on a 404), or say pending-after-reload is static text and a 15-minute-stale pending row shows as `failed`/retryable rather than "pending".
- [ ] **SHOULD** Goal 4 (sendBeacon) has no evidence behind it (assumption 6). Together with the injectable `nav` parameter, it is the main use of the brand-new vitest toolchain. — It's cheap, but it's the one part of the slice that solves a problem nobody has observed. — Either cite a case where a click was dropped, or downgrade it to "hardening" and keep it, knowing it doesn't feed the day-28 decision. Don't let it grow the scope.
- [ ] **NIT** Decision 3 says "each operation is a single upsert or delete statement". `set_vote` has to SELECT `rank_why` first so it can log at INFO, and the Interfaces describe `mark_clicked` as two statements. Reword it as "one `with self.conn:` block, no `_run` retry".
- [ ] **NIT** It's not said whether a vote change refreshes `source_label` and `keywords` from the current `rank_why` or keeps the first snapshot. This only matters for slice 2, but say which.
- [ ] **NIT** Pruning thumb rows by `created_at` at 180 days, when a re-tap keeps the original `created_at`, means a vote I re-affirmed recently can still be pruned. Pruning is also arguably YAGNI before slice 2 exists. Consider dropping `prune_signals` from this slice.
- [ ] **NIT** The rank_why AC compares the dict exactly with `"score": 1.2`, but `0.8 * 3.0 * 0.5 == 1.2000000000000002`. Use `pytest.approx` there too, as the score AC does.
- [ ] **NIT** The Files table says `getIngestStatus reuse`, but the existing function is `wikiIngestStatus` (`frontend/src/lib/api.ts:359`).
- [ ] **NIT** `SignalValue` and the CHECK constraints allow mismatched pairs such as (`thumb`, `save`). A table-level CHECK tying channel to value costs one line.

Cheaper alternative considered: The double-save guard could check the vault itself (`compiler.find_existing_by_source(wiki_dir, url)` before claiming), with an in-process dict of in-flight URLs. That would also cover pages saved through `/wiki/ingest` and pages deleted from the vault, and it drops the stale-claim and restart logic. You'd still want `feed_saves` (or a file-existence check) so `GET /feed` can show the saved state cheaply. So this trims the design rather than replacing it. Otherwise the slice is about as small as it can be. The only part I'd question as worth building is Goal 4.

What I checked:
- the spec
- the round-1 skeptic review
- `src/secondbrain/stores/feed.py`, `src/secondbrain/api/feed.py`, `src/secondbrain/api/wiki.py`
- `src/secondbrain/feed/rank.py`, `src/secondbrain/feed/pipeline.py`, `src/secondbrain/feed/models.py`, `src/secondbrain/feed/summarize.py` (summarize does not touch score, so `rank_why.score` stays valid after `update_summaries`)
- `src/secondbrain/ingestion/pipeline.py`, `src/secondbrain/ingestion/compiler.py` (`find_existing_by_source`)
- `src/secondbrain/models.py`
- `frontend/src/components/feed/FeedBlock.tsx`, `frontend/src/app/(dashboard)/feed/page.tsx`, `frontend/src/lib/api.ts`

All paths are under `/Users/brentrossin/code/second-brain/`.
