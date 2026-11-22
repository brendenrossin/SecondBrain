---
spec: 004-recall-hardening-from-the-spec-001-backlog.md
spec_version: 0.1.0
reviewer: architect
round: 1
verdict: approve with changes
date: '2026-11-22'
---
## Architect review — 004
Verdict: approve with changes

I traced POST /api/v1/recall through `src/secondbrain/api/recall.py` (steps 2–11), `HybridRetriever.retrieve` in `src/secondbrain/retrieval/hybrid.py`, the lifespan in `main.py`, `VectorStore._reconnect`/`_init_lock`, `mcp_server.base_url`, `recall_eval.validate_dataset`/`_post`/`evaluate`, the newsyslog conf, and the existing tests and goldens harness (`tests/fixtures/recall/capture_goldens.py`). The design fits how the code already works. `retrieve_vector_led` sharing a `_fuse` helper is the right size: `/ask` stays untouched, and recall passes `top_k = k_vec + K_LEX`, which covers every fused id, so the post-skip slice can't hide anything. No blockers. Four things should change before build.

- [x] **SHOULD** The 503 log line loses `witt_chunk_count` and `k_vec` when retrieval fails. Today `witt_chunk_count` is assigned in the handler before `retrieve` runs, so a 503 from embedder, Chroma or FTS still logs the real count and window. Under Decision 2, `_recall_work` only returns the count on success. If it raises, the handler's `except` logs `witt_chunk_count: 0, k_vec: 30` on exactly the lines you'd use for diagnosis. — Pass `_recall_work` a small mutable holder (or the `_Ranked`/a dict) and have it write the count into it before building the retriever. The `except` branch then reads it. Add a check to `test_retrieval_failures_return_503_without_leaking_internals` that the "embedder"/"chroma"/"fts" rows log `witt_chunk_count == 7`. — resolved: _recall_work writes witt_chunk_count to a holder before retrieving; 503 scenario outline asserts count 7 / k_vec 30 for embedder, chroma, fts

- [x] **SHOULD** Several existing tests in `tests/test_recall_api.py` hook `retrieve`/`_retrieve`. After the switch they break or, worse, pass without testing anything. The spec doesn't list them: — resolved: _retrieve is kept unchanged inside _recall_work, so spies and HybridRetriever patches stay valid; suppress_instrumentation stated; Files note lists the extended tests
  - The `spies` fixture wraps `recall_module._retrieve`. If `_retrieve` survives but is no longer called, `retrieve.assert_not_called()` in the non-local, unknown-project and empty-index tests passes trivially.
  - `test_snippets_truncated_on_a_word_boundary` and `test_vector_window_covers_every_witt_chunk_up_to_500` set `retriever_cls.return_value.retrieve.return_value`. A MagicMock `retrieve_vector_led` won't unpack into `(list, int)`, so they 503, and the window test's `retrieve.call_args` assert breaks.
  - `test_out_of_scope_candidates_dropped_even_if_a_store_misbehaves` overrides `retrieve` to drop `include_folders`. It will no longer inject an out-of-scope hit, and since `retrieve_vector_led` has no `None` default for `include_folders`, it can't be ported directly.

  — Fix: say that `_retrieve` is deleted (so a stale patch fails loudly) and the spy moves to `_recall_work` or `retrieve_vector_led`. Say whether `retrieve_vector_led` accepts `include_folders=None` or the misbehaving-store test fakes the store's `search` instead. List these rows in the Files note for `tests/test_recall_api.py`. Also state that `suppress_instrumentation()` still wraps the `retrieve_vector_led` call inside `_recall_work`; `test_recall_writes_zero_spans_with_tracing_on` guards it, but the spec doesn't say it.

- [x] **SHOULD** `validate_dataset(dataset)` drops its `corpus` argument, but tests rely on the corpus checks living there. `test_validation_exemptions_and_scoping` (the "null term only in 10_Notes" row checks corpus scoping) and `test_recall_queries_yaml_validates` both call `validate_dataset(dataset, corpus)`. Also, if `run_eval` calls a raising `validate_dataset` and then `corpus_problems`, a dataset with both kinds of fault reports only the structural reasons. That breaks today's "the message names every reason" contract. — Have a `structural_problems(dataset) -> list[str]` that `validate_dataset` wraps. `run_eval` joins both lists into one `DatasetError`. Move the scoping/exemption rows to `corpus_problems`. — resolved: validate_dataset keeps (dataset, corpus) and joins structural_problems + corpus_problems; exemption rows move to corpus_problems

- [x] **SHOULD** Goal 5 rollout is incomplete: — resolved: Rollout steps 2-4 cover the live-path check, the archive chmod and the sudo install
  - (a) Rotated archives `recall_log.jsonl.0`–`.2` are renames and keep 644. They hold the same query text, so chmod them too.
  - (b) The repo file `etc/newsyslog.d/secondbrain.conf` does nothing until it is copied to `/etc/newsyslog.d/`. Name that step.
  - (c) The conf hard-codes `/Users/brentrossin/code/second-brain/data/recall_log.jsonl`. `data_path` is relative to the API's `WorkingDirectory`, and spec 003 says the installed plists don't match the repo. Rollout should chmod the file the running API actually writes and confirm the conf points at it.

  — Add these three to the rollout/plan.

- [x] **NIT** `retrieve_vector_led`'s returned int should be pinned to mean lexical-only ids counted before the `top_k` slice. That is what recall needs, and it is equivalent today only because `top_k` covers every fused id. — resolved: count pinned to every lexical-only id before the top_k slice; top_k=2 scenario
- [x] **NIT** `_recall_work` must keep the `reader.db_path.exists()` guard before the first `conn` access, because `mode=ro` can't create the file. `test_missing_lexical_db_is_an_empty_index_not_a_503` will catch a slip, but the Decision 2 text drops it. — resolved: _recall_work step 1 keeps the db_path.exists() guard before any connection; missing-lexical.db scenario kept
- [x] **NIT** Goal 6 test: cancelling a task blocked in `to_thread` returns at once, but the worker thread stays blocked, and loop teardown waits on the default executor. The scenario's "blocks on an event" should release the event in teardown, or the test hangs for the wait timeout. Also clear `app.state.warmup_task` after the await so a reused app object doesn't carry a dead task into the next lifespan. — resolved: warmup scenario releases the event in finally; app.state.warmup_task cleared after the await
- [x] **NIT** The Goal 9 message for a JSON `[]` says "non-JSON body", which is inaccurate. Consider "non-object JSON body", or match on a shared prefix such as "recall api returned an invalid body". — resolved: shared prefix 'recall api returned an invalid body'
- [x] **NIT** The Goal 5 umask scenario must restore the process umask, since it is process-global and the suite shares one process. — resolved: umask scenario says the umask is restored afterwards

Decisions worth an ADR: Decision 4. Pytest stops gating live-corpus dataset drift and the recall eval (exit 2) becomes the only hard gate. That changes what `make check` promises and is cheap to reverse only if someone remembers to.
