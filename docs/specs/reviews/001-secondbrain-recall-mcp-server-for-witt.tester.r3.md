---
spec: 001-secondbrain-recall-mcp-server-for-witt.md
spec_version: 0.3.0
reviewer: tester
round: 3
verdict: approve with changes
date: '2026-11-21'
---
## Tester review — 001 SecondBrain recall MCP server for Witt (v0.3.0)
Verdict: approve with changes

Coverage: 9 goals, 60 scenarios, uncovered goals: none. Goal 4 (calibrated floor) and Goal 9 (eval) still have weak spots. The Intent claim "no network calls per query" has no scenario.

| Goal | Scenarios |
|---|---|
| 1 MCP, never raises | MCP x10 |
| 2 retrieval-only endpoint | endpoint x25, prefilter x7 |
| 3 project/kinds filters | kinds x2, project x2, unknown slug, vault missing, classification x2 |
| 4 floor + rescoring | floor boundary, floor before dedupe, keyword-only survives, unrelated query, explain |
| 5 skip Witt/Logs | ingestion x4 |
| 6 zero spans / no Langfuse | zero spans, Langfuse listener, unreachable Langfuse |
| 7 recall log | log schema, write failure, 503 row, no-writes, concurrency |
| 8 contracts unchanged | goldens, full suite, no weakening, trace-eval |
| 9 eval gates | metrics, gate table, overlap, API down |

- [x] **BLOCKER** The `explain` candidates are calibration's only input, and nothing pins their values. The explain scenario only says candidates "lists every retrieved candidate with similarity, bm25, score and dropped flags". — Broken implementation that passes: report `RetrievalCandidate.similarity_score` from before rescoring (0.0 for keyword-only chunks, `retrieval/hybrid.py:135`) and `dropped=False` everywhere. Then `null_max` leaves out keyword-only null candidates, the floor comes out too low, and every recall scenario still passes. — Extend `test_recall_explain_candidates`: floor 0.5, a vector chunk at 0.62, a vector chunk at 0.49, and a keyword-only chunk whose stored embedding scores 0.55. Assert the candidates' similarities are exactly 0.62, 0.49 and 0.55 (the rescored value, not 0.0), with `dropped` False, True and False. Pin whether candidates are listed before or after the project/kinds filters. Assert that `hits` are the same with `explain` true and false. — resolved: moot, since explain was removed in v0.4.0.

- [x] **SHOULD** The project filter has no prefix-collision case. Every fixture slug is a different string (`witt`, `second-brain`). — Broken implementation that passes: `note_path.startswith(f"Witt/Projects/{project}")` with no trailing slash, which leaks `Witt/Projects/witt-tools/...` into `project="witt"`. — Add a `Witt/Projects/witt-tools/specs/x.md` row to the Background. In `test_project_filter_excludes_prefix_sibling`, assert that `project="witt"` returns nothing under `witt-tools/`. — resolved: witt-tools prefix-sibling row and scenario; filter uses a trailing slash.

- [x] **SHOULD** No scenario combines `project` and `kinds`. — Broken implementation that passes: `if project: … elif kinds: …`, which applies only one filter. — `test_project_and_kinds_intersect`: `{"project": "witt", "kinds": ["decision"]}` returns exactly `[ADR-001-overrides.md]`, so the Learning and `scratch.md` are excluded. — resolved: project ∩ kinds scenario.

- [x] **SHOULD** Scope isolation relies entirely on the stores. `classify_witt_path("10_Notes/x.md")` returns `("other", None)`, and with no `kinds` filter step 7 keeps it. The Witt-only scenario passes whenever the mocked retriever honours `include_folders`. — Broken implementation that passes: any store bug that lets one non-Witt chunk through. The endpoint has no defence in depth and no test would notice. — Decide whether recall drops any candidate without the `Witt/` prefix after retrieval. If it should, add `test_recall_drops_non_witt_candidate_from_stub` with a retriever stub that ignores `include_folders` and returns `10_Notes/review-process.md`. Assert it is absent from the hits. — resolved: defence-in-depth drop of non-Witt paths with WARNING and dropped_out_of_scope (Decision 7 step 7 + stub scenario).

- [x] **SHOULD** `similarities()` correctness is only checked against hand-computed cosine. Its edge cases are unspecified at the recall level. — Broken implementations that pass: — resolved: moot, since similarities() was removed; keyword-only candidates are dropped by construction (Decision 6).
  - (a) A raw dot product, which passes when the fixture vectors are unit-norm.
  - (b) Calling `collection.get(ids=[])` when there are no keyword-only candidates. Chroma either raises (every such recall becomes a 503) or returns the whole collection.
  - (c) `sims[chunk_id]` on an id that Chroma lacks. This happens mid-reindex, because lexical and vector writes aren't atomic (`api/index.py:85-87,133-134`). It raises a KeyError, which the reindex scenario's "200 or 503" then hides.

  Fixes:
  - Use non-unit vectors in `test_similarities_cosine`, and assert `similarities([id], q)[id] == 1 - distance` from `search` for the same id (±1e-6), so both sides of the floor are on one scale.
  - Add `test_recall_no_keyword_only_candidates_skips_similarities`: `similarities` is not called, or is called with `[]` and returns `{}`.
  - Add `test_recall_keyword_only_missing_from_chroma_is_dropped`: the candidate is dropped and counted in `dropped_below_floor.keyword_only`, the response is 200, and nothing raises.

- [x] **SHOULD** The 503 table has no row for the new rescoring call. — Broken implementation that passes: calling `similarities()` outside the try/except, which turns a Chroma error into a 500 with a traceback and no recall_log line. — Add a row: "`VectorStore.similarities` raises ChromaError" → `recall unavailable: ChromaError`. Also pin what an unexpected exception type (for example a `KeyError` bug) returns, and whether it writes a recall_log line. Goal 7 only names 200 and 503. — resolved: catch-all Exception → 503 with log line; table adds count_chunks and KeyError rows.

- [x] **SHOULD** The snippet rule (Interfaces `RecallHit.snippet`) has no Gherkin scenario. r2 marked it resolved as "covered in tests/test_recall_api.py", but no scenario exists. — Broken implementations that pass: returning the full `chunk_text`, or `text[:600]` cutting mid-word. — `test_snippet_truncation`: a 100-char chunk is unchanged. A 1000-char chunk with spaces gives ≤600 chars ending at the last whitespace at or before 600. A 700-char chunk with no whitespace gives exactly 600 chars. — resolved: snippet truncation scenario added.

- [x] **SHOULD** "Embed the query once" (Decision 6 step 3) is only tested at the `retrieve` level. — Broken implementation that passes: recall embeds again for `similarities()`, which is two `embed_single` calls and twice the cost and latency. — In the endpoint test, assert `embed_single` is called exactly once per recall, and that the same array object goes to `retrieve(query_embedding=…)` and to `similarities(…, emb)`. — resolved: embed_single called exactly once asserted in the main scenario.

- [x] **SHOULD** The Langfuse scenario has no positive control and leaves out the keys. `init_tracing` attaches the OTLP processor only when `langfuse_public_key` and `langfuse_secret_key` are set (`tracing.py:103`). — Broken implementation that passes: a test fixture with no keys, so nothing is ever attached and "0 requests" holds trivially. — Set both keys. Before the recall, do one `/ask` (mocked LLMs) plus `force_flush`, and assert the listener got at least 1 POST to `/api/public/otel/v1/traces`. Then assert 0 new POSTs after the recall. — resolved: Langfuse scenario sets both keys and has an /ask positive control.

- [x] **SHOULD** The zero-spans scenario only turns on the chromadb instrumentor. Production calls `Traceloop.init` with its full default instrumentor set (`tracing.py:95`). — Broken implementation that passes: suppression placed so that only Chroma calls are covered, while another auto-instrumented library on the recall path still emits spans. — Run the subprocess through the real `init_tracing(settings)`, with `FileSpanExporter` swapped for an in-memory exporter behind a `SimpleSpanProcessor`. Keep the `/ask` control. — resolved: zero-spans runs through the real init_tracing with an in-memory exporter.

- [x] **SHOULD** The Intent property "no network calls per query with the default local embedder" has no scenario. — Broken implementation that passes: anything that does a per-request HTTP call (a probe, telemetry, a hub check). — `test_recall_makes_no_network_calls`: patch the model, warm it, then monkeypatch `socket.socket.connect` to raise. Assert the recall returns 200 and `connect` was never called. — resolved: no-network scenario with socket.connect patched to raise.

- [x] **SHOULD** The calibration drift warning is only tested for the mismatch case. — Broken implementations that pass: warning whenever the setting is non-empty, or comparing `settings.embedding_model`, which is still the local model name when `embedding_provider=openai`. — Parametrize `test_calibration_drift_warning` with these rows: — resolved: moot, since the drift check was removed with calibration.
  - Exact match: no warning.
  - Empty setting: no warning.
  - Same model with only `ctx` different: warning.
  - The openai provider, where the expected value uses the embedder's `model_name`, not `settings.embedding_model`.

- [x] **SHOULD** The `ge=0.3` floor validation is claimed (Decision 11) and never tested. — Broken implementation that passes: leaving out `ge=0.3`. — `test_recall_min_similarity_below_retriever_cut_rejected`: `Settings(recall_min_similarity=0.29)` raises a ValidationError, and 0.3 is accepted. — resolved: floor validation scenario (0.29 rejected, 0.3 accepted).

- [x] **SHOULD** The eval never enforces the dataset rules that make the held-out gate meaningful. These are split disjointness, the per-split minimums (≥4 null with ≥2 near-miss, ≥6 labelled with the listed mix), and "queries must not appear verbatim in any indexed note". — Broken implementation that passes: a YAML with the same query in both splits, or one null query. The held-out gate then becomes circular again. — `test_recall_eval_rejects_bad_dataset`, parametrized over overlapping splits, an undersized split and a verbatim query. Each exits non-zero with a named reason. — resolved: dataset validation scenario (counts, duplicate, verbatim, null contamination).

- [x] **SHOULD** The `stale_labels` gate can't be implemented as specified without guessing. The eval "never opens the stores", and no HTTP endpoint lists indexed note paths (`GET /api/v1/index/stats` returns counts only). — The gate-table row "an expected path missing from the index" doesn't say which response the stub has to fake. — Define the source. One option is "the expected path is not a file under `vault_path`, or matches `VaultConnector.DEFAULT_EXCLUDES`", since the eval already greps the vault. Another is a small read-only endpoint. Write the stub row against that source. — resolved: stale_labels source defined as a file under vault_path not matching DEFAULT_EXCLUDES.

- [x] **NIT** The 8-way concurrency scenario says "the embedder cold … loaded exactly once". State that the `SentenceTransformer` constructor is patched, otherwise the suite loads bge-base, which Decision 9 avoids. — resolved: SentenceTransformer constructor patched in the concurrency scenario.
- [x] **NIT** "Recall during a reindex" passes if every recall returns 503. Also assert that at least one recall returned 200, and that `_run_indexing` returned success without raising. — resolved: reindex scenario asserts at least one 200 and that _run_indexing completes.
- [x] **NIT** The keyword-only scenario should also assert `rescored_count == 1` in the recall_log line. No scenario checks that field. — resolved: moot, since rescoring was removed; dropped_keyword_only asserted instead.
- [x] **NIT** The unknown-slug scenario should assert one recall_log line with status 200 and that `embed_single` was not called. The vault-missing scenario covers only "not configured". Add a row for "configured but the directory doesn't exist", and assert the project filter still applies. — resolved: unknown-slug asserts a log line and no embed; vault-missing table covers both conditions.
- [x] **NIT** Classification has mismatches and gaps: — resolved: ** patterns in the kind table; sub-folder rows; 'known: none' scenario.
  - The kind table says `Witt/Learnings/*.md` but the project filter keeps `Witt/Learnings/**`. Pin the kind and project for `Witt/Learnings/sub/x.md` and `Witt/Projects/witt/specs/sub/x.md`.
  - Pin the warning text for a vault where `Witt/Projects/` is missing (empty known list).
- [x] **NIT** The calibration math fixture should include a case where the midpoint is below 0.3 (to exercise the `max`), a `null_max == labelled_min` case (overlap, since the comparison is strict `<`), and an expected note whose highest-similarity chunk is not its highest-RRF chunk, to pin which chunk "best chunk" means. — resolved: moot, since calibration math was removed.
- [x] **NIT** The `p95 latency 1200 ms` gate row needs a defined latency source: client wall clock with an injectable clock, or the server's `latency_ms`. A stubbed transport can't produce real wall-clock delay. `null_contamination` is in the gate table but missing from the "Hard gates" list in Evals, so add it there. — resolved: latency measured from server-side latency_ms; gate list consistent.
- [x] **NIT** Decision 8 says the MCP server logs `request_id` to stderr, and no test asserts it. Add it to the forwarding scenario using capsys stderr. — resolved: stderr request_id asserted in the forwarding scenario.

Files reviewed:
- /Users/brentrossin/code/second-brain/docs/specs/001-secondbrain-recall-mcp-server-for-witt.md
- /Users/brentrossin/code/second-brain/docs/specs/reviews/001-secondbrain-recall-mcp-server-for-witt.tester.r2.md
- /Users/brentrossin/code/second-brain/src/secondbrain/retrieval/hybrid.py
- /Users/brentrossin/code/second-brain/src/secondbrain/stores/vector.py
- /Users/brentrossin/code/second-brain/src/secondbrain/stores/lexical.py
- /Users/brentrossin/code/second-brain/src/secondbrain/stores/index_tracker.py
- /Users/brentrossin/code/second-brain/src/secondbrain/indexing/embedder.py
- /Users/brentrossin/code/second-brain/src/secondbrain/vault/connector.py
- /Users/brentrossin/code/second-brain/src/secondbrain/vault/parser.py
- /Users/brentrossin/code/second-brain/src/secondbrain/vault/__init__.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/index.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/dependencies.py
- /Users/brentrossin/code/second-brain/src/secondbrain/main.py
- /Users/brentrossin/code/second-brain/src/secondbrain/config.py
- /Users/brentrossin/code/second-brain/src/secondbrain/tracing.py
- /Users/brentrossin/code/second-brain/src/secondbrain/models.py (imports only)
- /Users/brentrossin/code/second-brain/src/secondbrain/__init__.py
