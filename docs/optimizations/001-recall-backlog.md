# Optimization backlog: spec 001 recall (feat/001-recall)

Deferred findings from the tri-review run on 2026-11-21 (Security Sentinel, Optimization Architect,
Quality Auditor). None was Critical or High. Fixes A–G from the same review were applied on the
branch.

Agreement: **2** = two personas raised it; **1** = one persona.

## Medium
- [ ] **Lexical-only candidates are fetched, then dropped** (1, Arch).
  - `HybridRetriever.retrieve` runs a `get_chunk` SELECT for each lexical-only id, up to `k_lex` = 50.
  - `api/recall.py::_rank` then drops all of them as keyword-only (similarity 0.0).
  - Fix: an opt-in `retrieve(..., vector_only_candidates=True)` that counts lexical-only ids without fetching them, keeping the `dropped_keyword_only` log counter.

## Low
- [ ] **Warmup task is never cancelled at shutdown** (2, Sec + Arch). `main.py` lifespan.
  - Cancelling can't interrupt the `to_thread` model load, so the gain is tidier shutdown logs only.
  - Fix: `task.cancel()` after `yield`, under `contextlib.suppress(asyncio.CancelledError)`.
- [ ] **The reader can close under a cancelled request's worker thread** (1, Sec). `api/recall.py`.
  - If the request is cancelled mid-retrieval, `finally: reader.close()` can run while the worker thread still uses it.
  - It's harmless, since the connection is read-only.
  - Fix: open and close the reader inside one worker function.
- [ ] **Project check sits outside the 503 catch-all and blocks the loop** (1, QA). `_check_project` does `iterdir` on the event loop.
  - A `PermissionError` there gives a bare 500 with no recall-log line.
  - Spec Decision 7 deliberately catches steps 4–11 only, so changing this is a spec change.
- [ ] **No per-entry length cap on `exclude_paths`** (1, Sec). Each entry is unbounded, and entries are echoed into the recall log. Fix: `len(p) <= 512` per entry. This is a spec change to `RecallFilters`.
- [ ] **Recall log permissions** (1, Sec). `recall_log.jsonl` is created 0644 and holds full query text, up to 2000 chars. It's fine for a single-user Mac. Create it 0600 if queries could be sensitive.
- [ ] **MCP error text echoes the API body** (1, Sec). Up to 500–1000 chars of a non-2xx body go into `error`. The trust level is the same as the API itself. Optionally label it as untrusted or truncate it harder.
- [ ] **Eval robustness** (1, QA).
  - `_post` doesn't guard `resp.json()`, so a non-JSON 200 gives a traceback instead of exit 3.
  - The report's `embedding_model` comes from local Settings, not from the serving API.
- [ ] **Settings are parsed on every MCP call** (1, Arch). `mcp_server.base_url()` runs `Settings()`, a `.env` read, per call. Cache it after the first success.
- [ ] **Chroma reconnect isn't locked** (1, Arch). `VectorStore._reconnect` and `_check_epoch` mutate `_client` and `_collection` without `_init_lock`. Init itself is safe; this is a narrow window on an external reindex. Fix: take `_init_lock` in `_reconnect`.
- [ ] **Per-request micro-costs** (1, Arch).
  - Two `to_thread` hops (count, then retrieve) could be fused into one.
  - The recall-log append is awaited before the response is returned.
  - The read-only connection is opened per request (sub-millisecond).
- [ ] **Snippet test rows** (1, QA). Add two rows: index 600 is whitespace, giving a 600-char snippet; and consecutive whitespace at the cut.
- [ ] **Precondition not asserted** (1, QA). "Witt-only recall returns the best decision first" doesn't assert that `10_Notes/review-process.md` is the closest match in the whole index, which the scenario presupposes.
- [ ] **The MRR recommendation still prints after the gate is on** (found 2026-11-21, after `gate_mrr: true`).
  - `recall_eval.evaluate` prints `recommend gate_mrr: true` whenever the corpus has more than 15 notes, even when the dataset already sets it.
  - Spec 001 Evals doesn't cover that case.
  - Fix: skip the recommendation when `dataset.gate_mrr` is true. This is a spec change.
- [ ] **The dataset-validation test reads the live vault** (found 2026-11-21). `test_recall_queries_yaml_validates` fails the suite whenever a new Witt note contains a null query's guard word. That happened with witt spec 006 and `react`. Decide whether the test should fail like this (it does catch drift) or warn.
