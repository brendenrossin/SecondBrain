---
spec: 004-recall-hardening-from-the-spec-001-backlog.md
spec_version: 0.2.0
reviewer: architect
round: 2
verdict: approve with changes
date: '2026-11-22'
---
## Architect review — 004 (r2)
Verdict: approve with changes

I traced the flow against `src/secondbrain/api/recall.py`, `retrieval/hybrid.py`, `stores/lexical.py`, `stores/vector.py`, `main.py`, `models.py`, `eval/recall_eval.py`, `etc/newsyslog.d/secondbrain.conf`, `pyproject.toml` and `tests/test_recall_api.py`. Decision 1's core claim holds:
- `HybridRetriever.retrieve` calls `lexical_store.get_chunk` only for ids missing from `vector_data` (hybrid.py:130-139).
- A `None` result is skipped before the `top_k` slice.
- `VectorStore.search` drops sub-floor ids before they get there, so "lexical-only" means exactly what the spec says.
- Lexical-only ids never add to a surviving candidate's RRF score.
- The 200 hits can't change, and `hybrid.py` does stay untouched.

The OUTSIDE note in `test_out_of_scope_candidates_dropped_even_if_a_store_misbehaves` is vector-backed (sim 0.95), so that test is unaffected. No blockers.

- [x] **SHOULD** Goal 4 depends on how `write_log` reads the count, and the spec doesn't pin it. Today `write_log` reads the closure local `witt_chunk_count` (recall.py:207, 222, 225). Decision 2 only says "the handler reads the holder after the call". On the 503 path, `to_thread(_recall_work)` raises, so there is no "after". An implementer who copies the holder into the local only on success would fail Goal 4 on embedder/Chroma/FTS failures. — Make the holder the only place the count lives. Create it before the `try`; have `write_log` and `respond` read `holder.witt_chunk_count` (and derive `k_vec` from it), and drop the local. — resolved: v0.3.0 — _RecallState holder is created before the try and is the only home of the count; write_log/respond read it and derive k_vec
- [x] **SHOULD** The spec says the "existing spies and retriever-class patches keep working", but renaming `_ReadOnlyLexicalStore` to `_VectorLedReader` breaks four direct references: the import at test_recall_api.py:13, line 297 (`patch.object(recall_module._ReadOnlyLexicalStore, "count_chunks", ...)`), line 646 (the `_inject` `conn` PropertyMock) and line 987. The `HybridRetriever` patches only keep working if `build_retriever` looks up the module-global `HybridRetriever` when it is called, not when the module is imported. — List the renamed references in the Files row for `tests/test_recall_api.py`. State that the `build_retriever` passed to `_recall_work` is a handler closure that calls `recall_module.HybridRetriever(...)`, so the patches on lines 298, 323, 476, 507 and 541 still bite. — resolved: renamed references listed in Files with no alias; build_retriever is a handler closure that looks up HybridRetriever at call time
- [x] **SHOULD** `check_live_dataset`'s "expected file missing" rule duplicates the eval's `stale_labels` gate (recall_eval.py:249), and the two disagree. The eval rule also fails on `_is_excluded(expected)`; the spec's rule only checks that the file exists. A label pointing at an excluded path would warn in pytest only if missing, yet fail the eval. Goal 12 also says the eval "fails on either (exit 2)", but a missing expected file is exit 1 (`stale_labels`), not exit 2. — Pull out one predicate, `_is_indexed_label(vault_path, expected)` (is_file and not excluded), use it in both places, and fix the Goal 12 wording so only structural and corpus problems give exit 2. — resolved: shared _is_indexed_label used by stale_labels and check_live_dataset; Goal 12 wording fixed (stale label = exit 1)
- [x] **NIT** `holder.lexical_only_skipped` is set "from the reader before it closes". Copying it in the `finally` that closes the reader is simpler and can't be missed on an early-return branch. — resolved: lexical_only_skipped is copied in the finally that closes the reader
- [x] **NIT** Decision 5's `c = self._collection or <create>` depends on a Chroma `Collection` being truthy. It is today (there's no `__len__` or `__bool__`), but write `if c is None` inside the lock to match the existing double-checked style and avoid depending on that. — resolved: explicit `is None` double-checked style in both properties
- [x] **NIT** With `get_chunk` stubbed out, a lexical-only out-of-scope id (from a misbehaving store that ignores `include_folders`) is now counted in `dropped_keyword_only`, not `dropped_out_of_scope`. That's harmless, but worth one line in the `_VectorLedReader` docstring next to the existing behaviour-difference note. — resolved: the docstring note about out-of-scope lexical-only ids is added to Decision 1
- [x] **NIT** The Risks section says the golden file may be committed "alongside" the `api/recall.py` change. A commit that has both can't show the goldens were captured on unchanged code. Require a separate, earlier commit. — resolved: goldens must land in their own earlier commit

Decisions worth an ADR: `make check` no longer gates live-corpus drift, and the eval is the hard gate (already planned in Decision 4). Also, recall's lexical reader deliberately returns `None` from `get_chunk` (vector-led retrieval without touching `hybrid.py`). Any future change to `HybridRetriever`'s fetch path has to respect that, so it is expensive to undo silently.
