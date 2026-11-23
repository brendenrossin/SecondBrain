---
spec: 006-feed-engagement-learning-and-save-to-vault.md
spec_version: 0.2.0
reviewer: tester
round: 2
verdict: approve with changes
date: '2026-11-22'
---
## Tester review — 006 Feed engagement learning and save to vault (v0.2.0)
Verdict: approve with changes

Coverage: 5 goals, 35 scenarios + 3 properties. Uncovered goals: none in code terms. Goal 5 (Measure) is a manual SQL check at day 28, which is fine for a product metric, but it is not acceptance. Goal 3 (Explain) and Goal 2's UI half (save states) are covered on the backend only. The round-1 blockers are resolved. The gaps that remain are mostly where a stubbed test passes while the real wiring is broken, plus the save-claim guarantee, which is only exercised one request at a time.

- [x] **BLOCKER** The claim's atomicity is only tested one request after another. "A double tap starts one job" seeds a pending row and then POSTs once. — A `claim_save` written as `SELECT …; if ok: INSERT OR REPLACE …` passes every scenario. Two taps run `to_thread(claim_save)` on two separate `FeedStore` connections at the same time, so both can see "no row" (or both can see an `error` row) and both start a paid KLIB-1 job. — Add `test_store_feed.py::test_claim_save_is_exclusive_under_concurrency`: two `FeedStore` instances on one db, a `threading.Barrier(2)`, both call `claim_save(url, now)`, repeated 50 times. Exactly one result has `.ok`, and the other has `.reason == "in_progress"`. Run it for a fresh url, a url whose row has an `error`, and a url whose claim is stale. — resolved: v0.3.0 Decision 4 makes claim_save one conditional upsert (SQL given). Added the 'Concurrent claims are exclusive' scenario (two stores, Barrier(2), 50 rounds, fresh/error/stale).

- [x] **BLOCKER** A retry claim may not clear the old `error`. The rule is that a claim succeeds when there is no row, the row has an `error`, or the claim is stale. In "A failed job is reported and can be retried", the scenario stops at "a new job starts". — An upsert that only resets `requested_at` leaves `error` set. GET then shows `save_state: "failed"` while the retry is running, and a third tap passes the claim again, so there are two jobs. — Extend that scenario and the stale-claim scenario: "And save_state is "pending" And a further POST returns 409 "save already in progress" And _start_ingestion_job was called exactly 2 times." Add `test_store_feed.py::test_claim_over_failed_row_resets_error_and_completed_at`. A matching check for `complete_save`: it must set `error = NULL`. — resolved: the claim upsert resets completed_at/wiki_path/error, and complete_save sets error NULL. The retry scenario now asserts pending, save_error null, a 409 on the third tap, and 2 jobs total.

- [x] **BLOCKER** Nothing checks that `on_complete` is called with the merged job. Every save-outcome scenario says "When on_complete runs", so the tests can call the callback directly with a hand-built job. — A refactor that calls `on_complete` before the merge (status still `FETCHING`, `error == ""`) passes. So does one that never calls it from the `except Exception` branch of `_run`, which leaves the claim stuck as pending for 15 minutes. — Add `test_wiki_api.py::test_on_complete_receives_merged_job`: stub `IngestionPipeline.run` to return `COMPLETE` with `result_path`, await the task, and assert the callback got `status == COMPLETE` and that `result_path`. Add `test_wiki_api.py::test_on_complete_called_when_pipeline_raises`: `pipeline.run` raises `RuntimeError("boom")`, and the callback gets `FAILED` with `error == "boom"`. — resolved: v0.3.0 Decision 4 runs on_complete in a finally after the status is final. Added 'Ingestion job callback' scenarios: merged COMPLETE job, pipeline raises → FAILED 'boom', failing callback logged.

- [ ] **SHOULD** The "job cannot start" scenario only covers the `HTTPException` path. Decision 4 also names "no Anthropic key", which makes `get_safety_auditor` raise `RuntimeError("Safety auditor requires SECONDBRAIN_ANTHROPIC_API_KEY")`. — An endpoint that does `except HTTPException: release_save(); raise` passes. Then the `RuntimeError` escapes with the claim still held and a bare "Internal Server Error". — Add `test_feed_api.py::test_save_without_anthropic_key_releases_claim`: 500, detail equal to that exact message, no `feed_saves` row, no save signal.

- [ ] **SHOULD** `wiki_path` is really an absolute path. `IngestionPipeline.run` sets `result_path = str(dest)`, which is `<vault_path>/Wiki/slug.md`. The scenarios use a stubbed `"Wiki/x.md"`, so they pass whether or not the path gets relativized, and the 409 detail and the "Saved (Wiki path)" label would expose the full filesystem path. — Decide which one is stored. Pin it with `test_feed_api.py::test_complete_save_stores_vault_relative_path`, which runs the real `on_complete` against a job whose `result_path` is `str(tmp_vault/"Wiki"/"x.md")`.

- [ ] **SHOULD** A pending save left by an API restart has no way out in the UI. After a reload, `save_state: "pending"` shows "Saving…" with no job_id to poll and no retry control (Decision 8 only offers retry on error). — Any implementation passes, because GET mapping of a stale claim is unspecified. — Either map a claim older than 15 minutes to `"failed"` (or `"none"`) in `get_recent`, or show retry when pending has no job. Add `test_feed_api.py::test_stale_pending_save_is_retryable_state`, plus a test that `get_recent` returns `"pending"` for a 1-minute claim (no scenario asserts the `"pending"` value through GET today).

- [ ] **SHOULD** A superseded job can overwrite the current claim. Job A goes stale and retry B starts. If A then fails, its `fail_save` sets `error` and releases B's claim, so a third tap starts job C. If A completes late, it marks the item saved while B is still running. — Nothing covers this. — Key `complete_save`/`fail_save` on the claim's `requested_at` (or a token). Add `test_store_feed.py::test_late_callback_from_superseded_claim_is_ignored`.

- [ ] **SHOULD** `mark_clicked` is two writes (`COALESCE clicked_at` plus the click signal insert). Decision 3 says "single statement", and only the vote path has a DB-failure scenario. Because "Given set_vote raises" mocks the store, "feed_signals unchanged" holds trivially there. — Two `_run` calls with a commit between them pass, and they leave `clicked_at` set with no signal row, so a first click is lost to slice 2. — Add `test_store_feed.py::test_mark_clicked_is_atomic_on_db_error`: inject `OperationalError` on the second statement and assert `clicked_at` is still NULL, no click row exists, and the error propagates. Also define the click endpoint's DB-error response and give it a scenario.

- [ ] **SHOULD** A step-5 failure in the save flow is undefined. If `record_signal(..., "save")` raises after the job has started, the job is already running and the claim is held. — A 500 here makes the UI show an error while the page still gets written. — Decide whether it is logged and swallowed (then return the job) or returned as a 500 with the claim kept, and add `test_feed_api.py::test_save_signal_failure_after_job_start`.

- [ ] **SHOULD** Votes fail in the degraded migration mode. `set_vote` copies keywords from `feed_items.rank_why`. If the v2 ALTER failed, that column does not exist, and the INSERT…SELECT raises "no such column", so every vote returns 500. "A failed migration degrades and retries" only checks `add_items` and GET. — Add the line "And voting on an item returns 200 with a thumb row whose keywords are []" to that scenario.

- [ ] **SHOULD** The snapshot is only asserted on the thumb row. — A click or save row written with `keywords '[]'`, or `source_label ''`, passes. — In "Only the first click is a signal" and "Saving starts one KLIB-1 job", also assert the row's `source_label` and `keywords` against the item's `rank_why`.

- [ ] **SHOULD** The "config keys verbatim" rule isn't tested by its own scenario. The upvote scenario uses lowercase "agents" and "claude", and `rank.py` lowercases keys when it builds patterns. — A `rank_why` that stores `kw.lower()` passes. — In the upvote scenario and the `rank_why` dict scenario, use a mixed-case key such as "Claude" and assert `"Claude"` comes back exactly.

- [ ] **SHOULD** "The API never reads the vault config" (Decision 2) has no proof. — A vote path that calls `load_feed_config` passes whenever a test vault exists. — Add `test_feed_api.py::test_vote_click_save_never_load_feed_config`: monkeypatch `secondbrain.feed.config.load_feed_config` to `pytest.fail`, set `vault_path=None`, and vote and click successfully.

- [ ] **SHOULD** The frontend scenarios cover only the negative cases. Nothing shows that clicking the anchor still calls `recordFeedClick(7)` (removing `onClick` passes). Nothing covers the why disclosure (it could render "undefined" or crash on `why: null`). Nothing covers save-state rendering: saved shows the path and no save button, failed shows the error and retry, and a 409 "already saved" reply is handled. The re-tap behaviour is unpinned: does tapping 👍 when the vote is already up send `"none"` or `"up"`? A rejected `voteFeedItem` is also unpinned, given that the backend 500 exists "so a dropped vote must not look accepted". — Add these `FeedBlock.test.tsx` tests: `anchor_click_records_click`, `why_lists_trust_keywords_recency`, `why_hidden_when_null`, `saved_state_shows_wiki_path`, `failed_state_offers_retry`, `retap_up_sends_none` (or the chosen behaviour), `vote_failure_reverts_toggle`.

- [ ] **SHOULD** In "Clearing a vote leaves click and save signals alone", the Given has no save row. — `DELETE … WHERE channel IN ('thumb','save')` passes. — Add a save row to the Given and assert that it is unchanged.

- [ ] **NIT** `0.8 * 3.0 * 0.5 == 1.2000000000000002`. The "rank_why explains the score" scenario compares an exact dict, so it fails on a correct implementation. Compare the numeric fields with `pytest.approx` (or compare `{**why, "score": pytest.approx(1.2)}`).
- [ ] **NIT** `recordFeedClick` can lose its `this` binding. `const send = nav.sendBeacon; send(url)` passes a `vi.fn` mock but throws "Illegal invocation" in real browsers. Assert `sendBeacon.mock.contexts[0] === nav`. Also cover `sendBeacon` throwing: the fallback should fire and nothing should propagate.
- [ ] **NIT** "No navigation happened" needs an observable check in jsdom. Assert `button.closest("a") === null` and that `voteFeedItem` is a `vi.mock("@/lib/api")` spy.
- [ ] **NIT** "The plain-text backfill did not run" needs an observable check. Seed the v1 db with a title containing `&amp;` and assert it is unchanged. Note that `test_fresh_database_is_marked_current` (`test_store_feed.py:344`) also asserts `== 1` and must become `== 2`, not be loosened.
- [ ] **NIT** The real migration race is not exercised. In it, `PRAGMA table_info` shows the column missing and then the ALTER raises "duplicate column name". The "already has a rank_why column" scenario only exercises the pre-check. Inject that exact `OperationalError` with the column present and assert `user_version == 2`.
- [ ] **NIT** The 15-minute stale boundary is tested at 1 and 16 minutes only. Add exactly 15:00 and pin whether the comparison is strict, since `claim_save` takes `now_iso` and this is cheap to do.
- [ ] **NIT** The response to `vote: "none"` is unpinned (`{"vote": "none"}` or `{"vote": null}`). So is "none" on an item that has no thumb row (expect 200, nothing changes). Vote and save behaviour when `feed_enabled=False` is unspecified too.
- [ ] **NIT** The day-28 query counts current rows. A vote cleared with "none", or an up flipped to down, leaves no trace, so "≥ 15 up+down" undercounts engagement. Accept that knowingly or add a note. A failed save's error text is not in `FeedItemResponse`, so after a reload the UI cannot show "the job's error". Either add `save_error` or narrow Decision 8.
- [ ] **NIT** For the FEED-1 order oracle property, state that the inputs have unique urls and that the comparison is on url sequence, so stable-sort ties are deterministic.
- [ ] **NIT** No Evals section is needed. There is no new LLM behaviour, and the save reuses KLIB-1.

Files read:
- /Users/brentrossin/code/second-brain/docs/specs/006-feed-engagement-learning-and-save-to-vault.md
- /Users/brentrossin/code/second-brain/docs/specs/reviews/006-feed-engagement-learning-and-save-to-vault.tester.r1.md
- /Users/brentrossin/code/second-brain/src/secondbrain/stores/feed.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/feed.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/wiki.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/dependencies.py
- /Users/brentrossin/code/second-brain/src/secondbrain/ingestion/pipeline.py
- /Users/brentrossin/code/second-brain/src/secondbrain/feed/rank.py
- /Users/brentrossin/code/second-brain/src/secondbrain/feed/pipeline.py
- /Users/brentrossin/code/second-brain/src/secondbrain/feed/models.py
- /Users/brentrossin/code/second-brain/src/secondbrain/models.py
- /Users/brentrossin/code/second-brain/frontend/src/components/feed/FeedBlock.tsx
- /Users/brentrossin/code/second-brain/frontend/src/app/(dashboard)/feed/page.tsx
- /Users/brentrossin/code/second-brain/frontend/src/lib/api.ts
- /Users/brentrossin/code/second-brain/tests/test_feed_api.py
- /Users/brentrossin/code/second-brain/tests/unit/feed/test_store_feed.py
