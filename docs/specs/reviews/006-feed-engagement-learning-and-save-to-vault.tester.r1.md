---
spec: 006-feed-engagement-learning-and-save-to-vault.md
spec_version: 0.1.0
reviewer: tester
round: 1
verdict: approve with changes
date: '2026-11-22'
---
## Tester review — 006 Feed engagement learning and save to vault
Verdict: approve with changes

Coverage: 5 goals, 24 scenarios + 4 properties. Uncovered goals: **Goal 5 (sendBeacon click capture) has no scenarios at all.** Goal 3 is covered on the API side only. Its UI half (why disclosure, two-step reset) has nothing. The core rule and store scenarios are specific and mostly well pinned. The blockers below are cases where a broken build would still pass the listed scenarios. The design itself is fine.

- [x] **BLOCKER** Keyword multipliers are never shown to reach a score. Scenarios check `compute_adjustments` keyword values and the pipeline source multiplier (0.7), but nothing checks that `rank_items` uses `m_kw` in `(1 + Σ weight_kw × m_kw)`. — A `rank_items` that ignores `adjustments.keyword` entirely passes every scenario. — Add `test_rank.py::test_keyword_multiplier_scales_interest_term`: trust 1.0, "agents" weight 2.0, recency pinned at 1.0, adjustments `keyword={"agents": 1.5}`. Expect score == 4.0 (vs 3.0 unadjusted), and `rank_why["keywords"] == [{"keyword": "agents", "weight": 2.0, "multiplier": 1.5}]`. That also pins the shape of the keywords entry, which the spec never defines. — resolved: rescoped. Slice 1 has no multipliers (the learning rule moves to spec 007). The rank_why keywords shape is pinned by the 'rank_why explains the score' scenario plus the Property.

- [x] **BLOCKER** "Byte-identical to FEED-1" is only checked as None == empty. Both `test_empty_adjustments_are_identity` and "No signals leaves ranking identical" compare `adjustments=None` with empty adjustments. The existing `test_rank.py` tests only assert ordering (`>`), never values. — A refactor that breaks the formula for both paths (drops the `1 +`, or applies recency twice) passes. — Add a golden-value test, `test_rank.py::test_score_matches_feed1_golden`: trust 0.8, "agents" 2.0, published exactly 48h before `now_ts` gives exactly 1.2, under None and under empty adjustments. — resolved: added the golden scenario 'Scores are unchanged from FEED-1' (1.2) and Property test_order_matches_feed1_oracle (independent oracle).

- [x] **BLOCKER** The vote, click, save and learning endpoints need the vault `interests` (for `matched_keywords`, and for dropping removed keywords in `/feed/learning`). The spec never says where the API gets them, or what happens if `vault_path` is unset. `load_feed_config(None / ...)` would raise TypeError. — An implementation that 500s every vote when the vault path is unset passes all scenarios. — Specify the source (e.g. `load_feed_config(settings.vault_path, settings.feed_config_path)`, falling back to seed defaults). Add `test_feed_api.py::test_vote_without_vault_path_records_signal_with_seed_or_empty_keywords`, and the same for `GET /feed/learning`. — resolved: v0.2.0 Decision 2. Signals snapshot keywords from rank_why, so no endpoint reads the vault config. /feed/learning moved to slice 2.

- [x] **BLOCKER** The single-transaction claim (Decision 5) has no test, and the store's retry pattern actively breaks it. `FeedStore._run` reconnects and retries one statement on `DatabaseError`. Reconnecting drops any uncommitted earlier statement, so `set_vote` built from two `_run` calls can commit only the second write. — Two separate writes, or `_run` + retry, pass every listed scenario and leave `feed_items.vote` and `feed_signals` disagreeing. — Add `test_store_feed.py::test_set_vote_is_atomic_on_db_error`: inject `sqlite3.OperationalError` on the second statement. Assert both tables are unchanged and the error propagates. Then add `test_feed_api.py::test_vote_db_failure_returns_500` with the body asserted, per Decision 7's "surfaces as a 500". — resolved: v0.2.0 Decision 3. Separate tables make each write a single statement in a `with self.conn:` block without _run retry. Scenario 'A database failure on vote is a 500'.

- [x] **BLOCKER** Save-flow ordering is not pinned, and the interface contradicts the 422 scenario. `mark_saved(item_id, keywords) -> url | None` both looks up and stamps. But "saved_at stays NULL" on a 422 needs the URL before stamping, and the store has no read-by-id method. — An implementation that calls `mark_saved` first, then `detect_content_type`/`_start_ingestion_job`, passes "Saving without a vault path" (it only asserts the 500). It leaves `saved_at` set and an `up` signal for a save that never started. — Add a `get_item(id)` (or equivalent) to Interfaces and fix the order: lookup → detect → start job → mark_saved. Extend the vault-path scenario: "and saved_at stays NULL, feed_items.vote and feed_signals are unchanged". Also extend the 404 and 422 scenarios with "feed_signals unchanged". — resolved: v0.2.0 Decision 4 ordered flow + get_item interface. 404, 422 and 500 scenarios assert feed_signals and feed_saves unchanged.

- [x] **BLOCKER** Goal 5 has no scenario, and there is no frontend test runner. Decision 6 has real branching logic (beacon → `false` → `fetch` keepalive; beacon missing → fetch). Manual testing is not acceptable for that. — `recordFeedClick` could keep the old `fetch` and every scenario still passes. — Either add a minimal vitest for `api.ts::recordFeedClick` (beacon returns true, so no fetch; returns false, so fetch with `keepalive: true`; undefined, so fetch), or extract it as a pure function with an injectable `navigator` and test that. Add a backend test too: `test_feed_api.py::test_click_accepts_beacon_shaped_request`. POST with `Content-Type: text/plain` and an empty body should give 200 and record the signal. — resolved: Brent chose to add vitest (+jsdom, RTL). recordFeedClick(id, nav) branch scenario, beacon-shaped POST backend scenario, and FeedBlock control scenarios.

- [x] **BLOCKER** The `GET /feed` never-raises claim is not proven for the new fields. `_to_item` runs outside `_fetch_recent`'s try. `row["vote"]` on a db whose v2 migration failed, or `json.loads` on a bad `rank_why`, would 500. — Direct `row["vote"]`/`json.loads(row["rank_why"])` passes all scenarios. — Add `test_feed_api.py::test_feed_serves_when_v2_columns_missing`: migration forced to fail, expect 200 with `vote: null, saved: false, why: null`. Add `test_feed_serves_with_malformed_rank_why`: expect 200 with `why: null`. Add `test_pre_feed2_rows_have_null_why`. — resolved: v0.2.0 Decision 6. Defensive rank_why parsing and joins inside _fetch_recent's try. Scenarios 'Malformed or missing rank_why' and 'A failed migration degrades and retries'.

- [ ] **SHOULD** "Saving starts a KLIB-1 job and counts as an upvote" only asserts `feed_items.vote`. "Saving keeps an existing downvote" only asserts `feed_items.vote == "down"`. — A `mark_saved` that sets the column but writes no signal (learning never fires) passes the first. One that upserts an `up` signal while leaving the column `down` passes the second. — Assert the `feed_signals` row kind ("up" in the first, still "down" in the second) and the row count. Add "save an item with only a click signal: row becomes 'up'" and "save twice: one signal row, two jobs".

- [ ] **SHOULD** A save whose KLIB-1 job later fails (fetch error, safety audit rejects) still leaves `saved_at` set and `saved: true` on the item, plus an `up` signal. — There is no scenario, so this behaviour is undefined rather than chosen. — Decide it, then pin it with `test_feed_api.py::test_failed_ingestion_job_effect_on_saved` (e.g. `saved` stays true but the UI shows the job error, or `saved_at` is cleared).

- [ ] **SHOULD** Signal pruning (Decision 2, 180 days) has no scenario. — `prune_signals` never called, or `DELETE FROM feed_signals` without a cutoff, passes. — Add `test_store_feed.py::test_prune_signals_drops_only_older_than_180_days` (181d gone, 179d kept, return value 1). Add `test_pipeline.py::test_refresh_prunes_signals`.

- [ ] **SHOULD** `vote: "none"` on an item that has only a click signal is undefined. Decision 5 says "clears … its thumbs signal", which implies the click survives. — A `DELETE ... WHERE item_url = ?` wipes the click and passes "Changing a vote". — Add `test_store_feed.py::test_vote_none_keeps_click_signal` (or decide the opposite and say so).

- [ ] **SHOULD** Re-tapping the same vote is undefined. — It may or may not refresh `created_at`, and refreshing it lets one vote stay at full weight forever. — Add `test_store_feed.py::test_repeat_up_vote_keeps_original_created_at` (or the chosen behaviour).

- [ ] **SHOULD** Reset semantics for `feed_items.vote` are unpinned. After `DELETE /feed/learning`, the thumbs stay lit, but no learning sits behind them. — Either choice passes the reset scenario. — Add an "And feed_items.vote is <NULL | unchanged>" line to "Reset deletes every signal".

- [ ] **SHOULD** `/feed/learning` sorting and keyword output are unchecked. The only scenario has one source and no keywords. — `keywords: []` always, or no sort at all, passes. — Add `test_feed_api.py::test_learning_lists_keywords_and_sorts_by_distance`: source A at 0.7, B at 1.2, keyword "agents" at 1.3. Expect sources order [A, B] and the keyword entry shape defined. Also define the failure mode of `GET /feed/learning` on a DB error (500 or empty), plus one scenario.

- [ ] **SHOULD** Migration coverage is v1→v2 only. — A build that re-runs the HTML backfill on v1 dbs, skips the v0 backfill when jumping v0→v2, or crashes on an already-present column passes. — Add `test_migrate_v0_to_v2_runs_backfill_and_adds_columns`, `test_v1_to_v2_does_not_rerun_backfill`, `test_migration_tolerates_existing_vote_column`, and "after a failed migration the next open retries and reaches v2". Also define "usable" in the failure scenario: `get_recent()` works and `GET /feed` returns 200. Existing `test_marks_the_database_migrated` must change to `== 2`, not be loosened to `>= 1`.

- [ ] **SHOULD** One bad `feed_signals` row (invalid keywords JSON, unknown kind) is unspecified. — `get_signals` raising on one row makes the refresh drop all learning, by way of the fail-soft path. — Add `test_store_feed.py::test_get_signals_skips_malformed_row`.

- [ ] **SHOULD** "Unreadable signals never abort" says "ranked with no adjustments" and "a warning is logged" without saying how to observe either. — Any log at any level, or partial adjustments, could be argued to pass. — Assert every stored `rank_why.source_multiplier == 1.0`, scores equal `rank_items(..., adjustments=None)`, and `caplog` has a WARNING from `secondbrain.feed.pipeline`.

- [ ] **SHOULD** `rank_why` persistence through the `add_items` upsert is untested. The `ON CONFLICT` clause lists its columns explicitly. — Inserting `rank_why` but not updating it on conflict gives a stale "why" from day 2 on, and the pipeline scenario (fresh db) still passes. — Add `test_store_feed.py::test_reupsert_refreshes_rank_why_and_preserves_vote_and_saved_at`. That also turns "a refreshed item I upvoted" into an explicit vote → re-refresh → still "up".

- [ ] **SHOULD** The Properties name Hypothesis, but `hypothesis` is not in `pyproject.toml`. "Order-independent" with exact equality will flake on float-sum reassociation. — Add the dev dependency. State that the order and bounds properties compare with `pytest.approx`/`math.isclose`, or that the implementation sorts before summing.

- [ ] **SHOULD** The UI behaviours have no acceptance. A vote/save tap inside the `<a>` wrapper must not navigate or fire `recordFeedClick`, or each 👍 also logs a click and opens a tab. Controls should be hidden when `id` is undefined (FeedBlock passes `stored?.id`). Save should be disabled when `safeHref` rejects. — With no test runner, any of these can regress silently. — Once vitest exists, add `FeedBlock.test.tsx::vote_button_does_not_open_link_or_record_click` and `::controls_hidden_without_id`.

- [ ] **NIT** The float assertions (1.3, 1.025, 1.05, 0.7, 1.2) should be specified as `pytest.approx`. `1 + 0.1*3` is `1.3000000000000003`. "Fresh" should mean `created_ts == now_ts` exactly.
- [ ] **NIT** "Only entries ≠ 1.0" needs a tolerance, or a near-cancelling up/down pair gets listed as 1.0000000001.
- [ ] **NIT** A future-dated `created_ts` (clock skew) gives decay > 1. Clamp age at 0 and extend the bounds property to negative ages.
- [ ] **NIT** `test_unknown_item_returns_404` (click) and the vote 404 test should also assert `feed_signals` is unchanged. Add "click → up → none → click again records no click signal" to exercise the `clicked_at IS NULL` guard. The unique index alone satisfies the current double-click scenario.
- [ ] **NIT** Name the patch target for the mocked KLIB-1 job (`secondbrain.api.feed._start_ingestion_job` vs `secondbrain.api.wiki._start_ingestion_job`). Note that `_start_ingestion_job` reads `get_settings()` directly, not through `Depends`, so the vault-path test must set the cached settings like `override_feed_settings` does.
- [ ] **NIT** Keyword case: say whether `matched_keywords` returns config keys verbatim or lowercased. If the vault note changes "Claude" to "claude", old signals silently stop matching.
- [ ] **NIT** Evals: no new LLM behaviour (save reuses KLIB-1), so an Evals section is not required. The day-28 product check is a fine product metric, not acceptance.

Files read:
- /Users/brentrossin/code/second-brain/docs/specs/006-feed-engagement-learning-and-save-to-vault.md
- /Users/brentrossin/code/second-brain/src/secondbrain/feed/rank.py
- /Users/brentrossin/code/second-brain/src/secondbrain/feed/pipeline.py
- /Users/brentrossin/code/second-brain/src/secondbrain/feed/models.py
- /Users/brentrossin/code/second-brain/src/secondbrain/feed/config.py
- /Users/brentrossin/code/second-brain/src/secondbrain/stores/feed.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/feed.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/wiki.py
- /Users/brentrossin/code/second-brain/src/secondbrain/ingestion/fetcher.py
- /Users/brentrossin/code/second-brain/src/secondbrain/models.py
- /Users/brentrossin/code/second-brain/frontend/src/components/feed/FeedBlock.tsx
- /Users/brentrossin/code/second-brain/frontend/src/lib/api.ts
- /Users/brentrossin/code/second-brain/tests/test_feed_api.py
- /Users/brentrossin/code/second-brain/tests/unit/feed/test_pipeline.py
- /Users/brentrossin/code/second-brain/tests/unit/feed/test_rank.py
- /Users/brentrossin/code/second-brain/tests/unit/feed/test_store_feed.py
