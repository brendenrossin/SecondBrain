# Feature: TraceEval Integration

**Date:** 2026-04-11
**Branch:** feat/eval-traceeval-integration (merged via PR #10)

## Summary

Integrated TraceEval-generated behavioral contracts into SecondBrain as both unit tests (49 tests across 5 components) and a behavioral eval (3 tests calling real Anthropic API). Added CI/CD pipeline that runs both on every PR.

## Problem / Motivation

TraceEval analyzed 321 real OTel spans from SecondBrain and identified 29 behavioral contracts across 5 components with 8 risk-ranked eval candidates. Several components (notably VectorStore) had zero test coverage. The analysis revealed that most findings were better served by deterministic unit tests rather than LLM evals — only the context blurb length constraint qualified as a true behavioral eval.

## Solution

Split TraceEval output into two tracks:
- **Unit tests** (`tests/traceeval/`): VectorStore CRUD, ChromaDB modify failure, task parsing edge cases, MetadataExtractor result parsing, model routing verification
- **Behavioral eval** (`evals/traceeval/`): Context blurb 1-2 sentence constraint with sentence-counting assertions (no LLM judge needed)

Both tracks run in CI via a dedicated `evals` job in `ci.yml`.

## Files Modified

**New test files:**
- `tests/traceeval/__init__.py`
- `tests/traceeval/test_vector_store.py` (18 tests)
- `tests/traceeval/test_vector_store_modify.py` (3 tests)
- `tests/traceeval/test_task_parsing_edges.py` (13 tests)
- `tests/traceeval/test_extractor_parsing.py` (9 tests)
- `tests/traceeval/test_model_routing.py` (6 tests)

**New eval files:**
- `evals/traceeval/test_context_blurb_constraint.py` (3 tests)
- `evals/traceeval/conftest.py` (real ContextGenerator fixture)
- `evals/traceeval/traceeval_helpers.py` (retained from TraceEval export)
- `evals/traceeval/README.md`

**Modified:**
- `src/secondbrain/stores/vector.py` — bugfix in `set_stored_model()`
- `pyproject.toml` — added `evals` to testpaths, registered `eval` marker
- `.github/workflows/ci.yml` — new `evals` job, lint/format now includes `evals/`
- `docs/ROADMAP.md` — added then delivered EVAL epic
- `CLAUDE.md` — updated active epics

## Key Decisions & Trade-offs

- **Unit tests over evals for deterministic behavior**: 6 of 8 TraceEval findings were better as unit tests. Only the context blurb length constraint (LLM output quality) warranted a real eval. This keeps the test suite fast and free to run.
- **Sentence counting over LLM judge**: The behavioral contract is "1-2 sentences" which is countable. No need for an expensive LLM-as-judge pattern. Can add quality judging later.
- **Dropped HTTP client tests (EVAL-008)**: Low risk, network-dependent, flaky. Not worth the maintenance cost.
- **Dropped performance benchmarks (EVAL-004/005)**: Timing tests are environment-dependent and noisy.
- **Separate `tests/traceeval/` directory**: Keeps TraceEval-derived tests grouped by provenance rather than mixed into existing test files. Makes it clear which tests came from trace analysis.

## Patterns Established

- **Eval files live in `evals/`**, separate from unit tests in `tests/`. Evals may require API keys and cost money; unit tests are always free and fast.
- **`@pytest.mark.eval` marker** for LLM evals that need API keys. Registered in `pyproject.toml`.
- **conftest.py checks both `ANTHROPIC_API_KEY` and `SECONDBRAIN_ANTHROPIC_API_KEY`** — covers both CI (standard name) and local dev (project-prefixed name).
- **CI `evals` job** runs independently of the `check` job. Both must pass for PRs.

## Testing

- 49 unit tests: all deterministic, no API calls, run in ~0.5s
- 3 behavioral evals: real Anthropic Haiku calls, ~4s, ~$0.02 per run
- Full suite: 714 tests pass with 0 regressions
- CI verified: `check` job passes, `evals` job passes (evals skip gracefully when secret not set)

## Future Considerations

- **Regenerate evals as traces accumulate**: Run `traceeval export` periodically to discover new behavioral contracts from production traces.
- **LLM judge for quality**: Current eval only checks sentence count. Could add coherence/relevance judging if blurb quality becomes a concern.
- **TraceEval as a general SDLC tool**: The unexpected outcome was that TraceEval is better for identifying unit test gaps than generating evals. Worth exploring this angle in TraceEval's own roadmap.
- **Real bug found**: `set_stored_model()` was silently failing because it included `hnsw:space` in the ChromaDB `modify()` payload. The exception was swallowed. Fixed by removing the redundant key.
