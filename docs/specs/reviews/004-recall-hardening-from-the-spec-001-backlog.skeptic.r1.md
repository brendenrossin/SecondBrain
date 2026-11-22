---
spec: 004-recall-hardening-from-the-spec-001-backlog.md
spec_version: 0.1.0
reviewer: skeptic
round: 1
verdict: approve with changes
date: '2026-11-22'
---
## Skeptic review — 004
Verdict: approve with changes

Unstated assumptions:
1. "The recall goldens" already exist. They don't. `tests/fixtures/recall/goldens.json` holds only unfiltered `retrieve` / `search` outputs from default-constructed retrievers, with no `include_folders`, no recall floor and no recall hits. Not written down. The Risks section only says the plan will capture a `retrieve` golden.
2. The fixture index has a query with "3 lexical-only Witt chunks and 4 vector hits". The fixture has 7 Witt chunks, but nothing shows TEST_QUERY splits 3/4 under `recall_min_similarity`. Not written down.
3. Golden comparisons must sort RRF ties, because `retrieve` iterates a `set`, so tie order changes with the hash seed. `capture_goldens.py` already sorts ties by `(-rrf, chunk_id)`, but the spec's "byte-identical" wording doesn't say so. Not written down.
4. `_recall_work` still runs under `suppress_instrumentation()` (spec 001 Decision 8). The Design and flowchart never mention it. Not written down.
5. Editing `etc/newsyslog.d/secondbrain.conf` changes the installed rotation. It only does so if the file is re-copied into `/etc/newsyslog.d/` with sudo, which is the same repo-vs-installed drift spec 003 exists to fix. Not written down. Rollout only mentions a chmod.
6. Pytest doesn't escalate warnings to errors. I checked: `pyproject.toml` has no `filterwarnings`. So it holds today, but it isn't stated as a constraint for Decision 4.
7. Taking the lock in `_reconnect` makes `VectorStore` safe. The `client` and `collection` fast paths read `self._client` / `self._collection` outside the lock (`if x is None: ...; return x`). A concurrent `_reconnect` can still null the attribute between the check and the return, so the caller gets `None`. Not written down.

- [x] **BLOCKER** Goal 1's safety net points at an artifact that doesn't exist. The Non-Goals and the Goal 1 scenario say "the recall goldens must not change" / "hits equal the stored recall goldens", but no recall-hit golden is stored anywhere. The "/ask retrieve golden with include_folders=["Witt"]" doesn't exist either. — Decision 1 is the only change here that can silently move `/ask` ranking, and its regression check is undefined. Two engineers will capture different things (raw vs tie-sorted, which floor, which queries), or capture after the refactor. — Fix: name the files and how they're captured. For example: `goldens.json` gains `retrieve_witt` (TEST_QUERY + GOLDEN_QUERIES, `include_folders=["Witt"]`, `min_similarity=settings default`), and a new `recall_goldens.json` holds the hits from `POST /recall`. Both are captured by `capture_goldens.py` on unchanged code in plan step 1, with ties sorted by `(-round5(rrf), chunk_id)`. Also confirm, or build and name, the 3-lexical-only/4-vector fixture query. — resolved: v0.2.0 adds recall_goldens.json (endpoint hits, TEST_QUERY + LEXONLY_QUERY, each filter) captured by capture_goldens.py on unchanged code, ties sorted; LEXONLY fixture named (4 vector + 3 lexical-only); hybrid.py no longer changes, so no /ask golden is needed

- [x] **SHOULD** A much cheaper way to do Goal 1 is available, and the spec doesn't weigh it. `retrieve` already skips any lexical-only id whose `get_chunk` returns `None`. Override `get_chunk` on `_ReadOnlyLexicalStore` (recall-only) to count the call and return `None`, and every lexical-only fetch disappears with zero changes to `hybrid.py`, no `_fuse` refactor and no `/ask` risk. The saving is at most 50 local SQLite primary-key lookups, a few ms. A new public method plus a shared-helper refactor is a lot of risk for that. — Fix: either pick the override, or record why it was rejected (for example, "a store that lies about get_chunk is a trap"). Otherwise, consider deferring Goal 1 entirely. — resolved: adopted — _VectorLedReader.get_chunk counts and returns None; hybrid.py untouched; rejection of r0 design recorded in Decision 1

- [x] **SHOULD** `retrieve_vector_led`'s contract is underspecified. (a) Is `top_k` applied before or after lexical-only ids are removed, and does the returned int count ids beyond the cut? It makes no difference at recall's `top_k = k_vec + K_LEX`, but it's a public method. (b) Is `include_folders` required, or can it be `None`? The signature has no default, but the AC only covers `[]`. (c) Recall "sets `dropped_keyword_only` from the returned int", while `_rank` still increments the same counter in its guard. Overwrite or sum? — Fix: state all three. Suggest: `top_k` slices vector-backed candidates only; the int counts every lexical-only id; `include_folders` is required and non-empty; `dropped_keyword_only = skipped + ranked.dropped_keyword_only`. — resolved: moot under the override; count semantics pinned (every lexical-only id, before top_k) plus a top_k=2 scenario; dropped_keyword_only = reader count + _rank guard

- [x] **SHOULD** The Intent understates what 004 supersedes in spec 001. It lists four items. Goal 1 also changes 001 Decision 7 steps 5–6: the call becomes `retrieve_vector_led`, and the count semantics change for ids whose `get_chunk` would return `None`. Goal 2 changes the "Any exception in steps 4–11" sentence. — Fix: list Decision 7 steps 5, 6 and the catch-all sentence among the superseded items. — resolved: Intent now lists Decision 7 steps 3-6 and the catch-all sentence

- [x] **SHOULD** Decision 2 must keep `suppress_instrumentation()`. Today only `retrieve` runs under it. When count and retrieve merge into `_recall_work`, the spec should say the whole function, or at least the retrieve, stays inside it. `test_recall_writes_zero_spans_with_tracing_on` would catch a slip, but the spec shouldn't rely on that. — Fix: add one line to Decision 2 and show it in the flowchart. — resolved: Decision 2 and the flowchart keep _retrieve under suppress_instrumentation; zero-spans scenario added

- [x] **SHOULD** Decision 4 loses reasons. If `validate_dataset` raises, `corpus_problems` never runs, so the eval's DatasetError no longer "names every broken rule" (the current docstring promise and 001 behaviour). — Fix: add a `structural_problems(dataset) -> list[str]` and keep `validate_dataset` as a thin raiser over it. `run_eval` joins both lists into one `DatasetError`. — resolved: structural_problems + corpus_problems; validate_dataset joins both and names every reason; scenario added

- [x] **SHOULD** Goal 7 as written doesn't close the race the backlog describes. Locking `_reconnect` serialises it against lazy init, but the unlocked fast-path read in `client` / `collection` can still return `None` mid-reconnect. `_check_epoch` (named in the backlog) is also unlocked. The AC only proves the lock is taken. — Fix: either read into a local under the lock in both properties (`c = self._collection; if c is None: with lock: ...; return c`) and add an AC for it, or state the remaining window explicitly and keep Goal 7 as "narrowed, not closed". — resolved: Goal 8 now closes the race — properties read into locals, _reconnect locked; lock-held, re-entrancy and stress scenarios

- [x] **SHOULD** Goal 5's rollout needs a step to install the newsyslog change. — Fix: add "copy the conf into `/etc/newsyslog.d/` (sudo) and diff it against the repo copy" to rollout, and say whether archived rotations (`.0`, `.1`, …) already on disk get a chmod. — resolved: Rollout adds the sudo copy + diff, and a chmod of rotated archives

- [x] **SHOULD** The second snippet scenario tests nothing new. With spaces at 597–603, `text[600]` is a space, so it takes exactly the same branch as the first scenario and gives the same `text[:600]`. That snippet also ends in three trailing spaces, so the scenario title "ends at the last space" doesn't match what is pinned. — Fix: use a run that ends before 600 with no whitespace at 599–600 (for example, spaces at 590–594, expect `text[:594]`). Also state whether trailing whitespace in a snippet is intended. — resolved: second snippet row is now spaces at 590-594, expecting text[:594] with trailing spaces kept (no rstrip)

- [x] **NIT** Goal 9 sends `[]` (valid JSON) to the same "non-JSON body" message. Use "a non-object JSON body", or a neutral "an unexpected body". — resolved: message is now 'recall api returned an invalid body (expected a JSON object)'
- [x] **NIT** Goal 10 labels `embedding_model` but not `hf_revision`, which is equally read from the eval process's local HF cache. Label both, or rename the key `"model_fields_source"`. — resolved: model_fields_source covers embedding_model and hf_revision
- [x] **NIT** Goal 8 is of doubtful value. It saves one `.env` parse per MCP call (about 1 ms against a network round trip) and adds stale-config behaviour plus a test fixture. Fine to keep, but it's the first one to cut if the batch feels big. — resolved: Goal 8 (MCP base_url cache) cut at triage; moved to Non-Goals, stays on the backlog

Cheaper alternative considered: For Goal 1, override `get_chunk` on recall's `_ReadOnlyLexicalStore` to count and return `None`. That gives the same counter and no fetches, without touching `hybrid.py` or putting `/ask` goldens at risk. The rest of the batch is already minimal per item. Goal 12 is the only item that hurts today and could ship alone.

Files reviewed:
- docs/specs/004-recall-hardening-from-the-spec-001-backlog.md
- docs/specs/001-secondbrain-recall-mcp-server-for-witt.md (Decisions 7–9, 11; Evals)
- docs/optimizations/001-recall-backlog.md
- src/secondbrain/api/recall.py, retrieval/hybrid.py, stores/vector.py, main.py, mcp_server.py, models.py (RecallFilters), eval/recall_eval.py
- etc/newsyslog.d/secondbrain.conf
- tests/test_recall_eval.py, tests/test_recall_prefilter.py, tests/test_recall_api.py, tests/fixtures/recall/capture_goldens.py
- pyproject.toml (pytest config)
