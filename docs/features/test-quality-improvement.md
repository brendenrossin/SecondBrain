# Test Quality Improvement — Replace Pure Mocks, Add Integration Coverage

> **Status:** Planned
> **Estimated effort:** 2-3 days
> **Depends on:** None (can be done independently)

## Problem

The test suite has 453 tests, but quality is uneven:

- **~14 "pure mock" tests** across 4 files (`test_main.py`, `test_health.py`, `test_admin_api.py`, `test_api_latency.py`) would pass even if the underlying code was deleted. They test mocking wiring, not business logic.
- **No end-to-end retrieval test** — the core RAG pipeline (index → retrieve → rerank → synthesize) has zero integration test coverage. A breaking change in any step would not be caught.
- **API tests over-mock internal functions** — `test_briefing_api.py`, `test_tasks_api.py`, and `test_events_api.py` mock out the actual scanning/aggregation logic and only test vault availability checks. The real endpoint behavior (parsing files, aggregating data, formatting responses) is untested at the API layer.
- **No error recovery tests** — LLM API timeout, vector store corruption, and embedding failures have no test coverage.

The CI was already broken for weeks by a subtle mock targeting bug in `test_api_latency.py` (patching `secondbrain.config.get_settings` instead of using `app.dependency_overrides`). This went unnoticed because "those tests always fail" — a direct consequence of poor test quality eroding trust in CI.

## Solution

Three work items in priority order. Each is independently valuable and can be shipped separately.

### Work Item 1: Replace pure mock tests with functional tests

**Goal:** Every test should fail if the code it claims to test is broken.

**Behavior:**

1. **`test_main.py`** (3 tests) — Replace with tests that exercise the actual FastAPI `lifespan` startup:
   - Test that `app` startup logs vault path when configured (use `tmp_path` with real settings)
   - Test that `app` startup logs error when vault path is None
   - Test that `app` startup logs error when vault path doesn't exist
   - Use `TestClient(app)` which triggers lifespan, not mocked `get_settings`

2. **`test_health.py`** (2 tests) — Replace with tests that use `app.dependency_overrides`:
   - Test health returns OK with vault that exists (use `tmp_path`)
   - Test health returns degraded/error status when vault doesn't exist
   - Verify disk space and sync freshness fields are populated from real data

3. **`test_admin_api.py`** (4+ tests) — Use real SQLite stores with `tmp_path`:
   - Create real `UsageStore`, `QueryLogger`, `ConversationStore`, `IndexTracker` backed by temp databases
   - Insert a few records, then hit the API and verify the response reflects actual data
   - Test date range filtering with real timestamps

4. **`test_api_latency.py`** (5 tests) — Already fixed (dependency overrides + real path). Document that these tests measure framework overhead, not business logic, and are intentionally mock-heavy. Add a comment explaining the test's purpose.

**Files:** `tests/test_main.py`, `tests/test_health.py`, `tests/test_admin_api.py`, `tests/test_api_latency.py`

### Work Item 2: Add end-to-end retrieval integration test

**Goal:** One test that exercises the full RAG pipeline from indexing through answer synthesis, catching regressions in the core value path.

**Behavior:**

- Create `tests/test_retrieval_e2e.py` with a self-contained test that:
  1. Creates 5 markdown files in `tmp_path` with known content spanning different topics
  2. Indexes them using the real `Indexer` (real chunker, real embeddings with a small local model or mocked embedding provider that returns deterministic vectors)
  3. Queries with `RetrievalService` using hybrid search
  4. Verifies top results contain the expected chunks (correct file, correct heading)
  5. Verifies citation metadata is correct (note_path, heading_path)
- A second test for incremental reindex:
  1. Index 3 files
  2. Modify one file's content
  3. Reindex
  4. Verify retrieval returns updated content, not stale chunks

**Mocking strategy:** Mock only the embedding provider to return deterministic vectors (avoids downloading a model in CI). Everything else runs for real — chunker, stores, FTS5, vector similarity, RRF fusion.

**Files:** `tests/test_retrieval_e2e.py` (new)

### Work Item 3: Improve API endpoint test coverage

**Goal:** API tests should exercise real endpoint logic, not just vault availability checks.

**Behavior:**

1. **`test_briefing_api.py`** — Add tests with real daily notes in `tmp_path`:
   - Create daily notes with tasks and events
   - Hit `GET /api/v1/briefing` with `app.dependency_overrides` pointing `vault_path` to `tmp_path`
   - Verify response includes parsed tasks and events from the real files

2. **`test_tasks_api.py`** — Add tests with real daily notes:
   - Create daily notes with various task states (open, in-progress, done)
   - Hit `GET /api/v1/tasks` and verify correct aggregation
   - Hit `PATCH /api/v1/tasks/update` and verify the file is actually modified

3. **`test_events_api.py`** — Add tests with real daily notes:
   - Create daily notes with events
   - Hit `GET /api/v1/events?start=...&end=...` and verify correct parsing

**Mocking strategy:** Only mock `get_settings` via `app.dependency_overrides` (pointing vault to `tmp_path`). No mocking of internal scanning/aggregation functions.

**Files:** `tests/test_briefing_api.py`, `tests/test_tasks_api.py`, `tests/test_events_api.py`

## Implementation Order

1. WI1 (replace pure mocks) — Quick wins, builds confidence in CI
2. WI2 (e2e retrieval) — Highest risk coverage gap
3. WI3 (API endpoint tests) — Broader coverage improvement

All three are independent and can be parallelized.

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| Rewriting all mock-heavy tests | Diminishing returns. Focus on pure mocks and highest-risk gaps. |
| Adding concurrency/load tests | Useful but requires test infrastructure (async test client, timing assertions). Defer to a separate work item. |
| LLM integration tests with recorded responses | Requires VCR-style recording infrastructure. Defer until the test foundation is solid. |
| Frontend test coverage | Different toolchain (Jest/Vitest). Separate work item. |
| Test coverage metrics / reporting | Nice-to-have tooling. Not the bottleneck. |

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| E2e retrieval test is slow (embedding model download) | Medium — CI timeout | Mock embedding provider with deterministic vectors |
| Real SQLite tests leave temp files | Low — pytest `tmp_path` auto-cleans | Use `tmp_path` consistently |
| Functional API tests are brittle to response format changes | Low — expected | Test key fields, not exact JSON structure |

## Testing

This IS the testing improvement. Success criteria:
- 0 pure mock tests remaining (all 14 replaced with functional equivalents)
- At least 1 end-to-end retrieval test that would catch a broken indexing or retrieval pipeline
- API endpoint tests that exercise real file parsing, not just vault availability
- `make check` still passes in < 30 seconds
- CI goes green and stays green

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Mock only embedding provider in e2e test | Downloading models in CI is fragile and slow. Deterministic vectors still test the full pipeline. |
| Use `app.dependency_overrides` consistently | FastAPI's official test mechanism. Avoids the `@lru_cache` patching bug that broke CI. |
| Keep `test_api_latency.py` mock-heavy | These tests intentionally measure framework overhead, not business logic. The mocking is the point. Just needs documentation. |
| Improve existing test files, not create new ones (except e2e) | Avoids file proliferation. The existing files have the right names and structure. |
