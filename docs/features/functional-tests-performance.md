# Functional Test Overhaul + Server Performance Hardening

> **Status:** In Progress
> **Estimated effort:** 2–3 sessions
> **Depends on:** None (standalone quality + reliability initiative)

## Problem

### Test Suite is Mock-Heavy
Of ~350 tests across 26 files, roughly a third would pass even if the underlying code was completely broken. The critical path — vault parsing → chunking → hybrid search → reranking → answer — has **zero** end-to-end functional tests. This means regressions in core business logic (note parsing, task aggregation, event extraction, search quality) go undetected.

**Specific gaps:**
- No tests for `vault/parser.py` title extraction logic
- No tests for `indexing/chunker.py` heading hierarchy or chunk ID stability
- No tests for hybrid RRF formula correctness
- No tests for reranker JSON parse → regex → similarity fallback chain
- No API latency benchmarks

### Server Unresponsive Over Tailscale
The server becomes unresponsive when accessed from a phone over Tailscale. Root causes:

1. **Blocking sync operations in async handlers** — Retrieval, reranking, file scanning all block the uvicorn event loop
2. **No timeouts on LLM API calls** — A slow Anthropic/OpenAI call hangs indefinitely
3. **Admin stats fetches 10,000 conversations** with nested COUNT subqueries
4. **No frontend fetch timeouts** — Requests hang until browser gives up

## Solution

Two work streams executed together.

---

### Work Stream A: Functional Tests

#### WA-1: Note Parsing Tests
**Goal:** Validate `vault/parser.py` title extraction precedence and edge cases.
**File:** `tests/test_parser.py` (new)
**Tests:**
- Title from frontmatter field
- Title from first H1 heading (not H2)
- Title from filename (fallback)
- Non-string frontmatter title (list, dict) → skipped
- Empty content → filename fallback
- Multiple H1 headings → only first used
- Frontmatter with no title key

#### WA-2: Chunking Logic Tests
**Goal:** Validate `indexing/chunker.py` heading hierarchy, splitting, and ID stability.
**File:** `tests/test_chunker.py` (new)
**Tests:**
- Heading path tracking (H1 → H2 → H3 nesting)
- Heading level reset (H3 back to H2)
- Content assigned to correct heading path
- Trailing content after last heading
- Large section recursive splitting
- Force split with word boundary + overlap
- Min chunk size filtering
- Chunk ID stability (same input → same hash)
- Chunk ID changes when content changes
- Empty note → no chunks
- No headings → single chunk with empty path

#### WA-3: Hybrid Search RRF Tests
**Goal:** Validate `retrieval/hybrid.py` RRF formula and ranking logic.
**File:** `tests/test_hybrid_rrf.py` (new)
**Tests:**
- RRF score calculation with known ranks
- Chunks in both vector + lexical rank higher than single-source
- Lexical-only chunks get metadata from lexical store fallback
- Empty query → empty results
- Single result from one source only
- Heading path pipe-delimited deserialization

#### WA-4: Reranker Fallback Chain Tests
**Goal:** Validate `retrieval/reranker.py` score parsing and label logic.
**File:** `tests/test_reranker_logic.py` (new)
**Tests:**
- Valid JSON array → scores used directly
- Invalid JSON → regex number extraction fallback
- Neither JSON nor regex → similarity * 10 fallback
- Wrong-length JSON array → regex fallback
- Hallucination detection (similarity > 0.7, rerank < 3.0)
- Retrieval labels: PASS, NO_RESULTS, IRRELEVANT, HALLUCINATION_RISK
- Empty candidates → NO_RESULTS label
- LLM exception → similarity fallback

#### WA-5: API Latency Benchmark Tests
**Goal:** Assert key endpoints respond within time budgets.
**File:** `tests/test_api_latency.py` (new)
**Tests:**
- `/health` < 100ms
- `/api/v1/tasks` < 2s (with mocked vault)
- `/api/v1/events` < 2s (with mocked vault)
- `/api/v1/briefing` < 2s (with mocked vault)
- `/api/v1/admin/stats` < 1s (with mocked stores)

---

### Work Stream B: Server Performance Hardening

#### WB-1: Async Wrapping for Blocking Endpoints
**Goal:** Prevent sync operations from blocking the uvicorn event loop.
**Files:** `api/ask.py`, `api/briefing.py`, `api/tasks.py`, `api/events.py`
**Changes:**
- Wrap `retriever.retrieve()`, `reranker.rerank()`, `answerer.answer()` in `asyncio.to_thread()`
- Wrap `scan_daily_notes()`, `aggregate_tasks()`, `get_events_in_range()` in `asyncio.to_thread()`
- Wrap `_build_briefing()` in `asyncio.to_thread()`

#### WB-2: LLM API Timeouts
**Goal:** Prevent hung requests when Anthropic/OpenAI is slow.
**Files:** `retrieval/reranker.py`, `synthesis/answerer.py`
**Changes:**
- Add `timeout=httpx.Timeout(60.0)` to Anthropic client initialization
- Add `timeout=60.0` to OpenAI client initialization

#### WB-3: Frontend Fetch Timeouts
**Goal:** Prevent indefinite hangs in the browser.
**File:** `frontend/src/lib/api.ts`
**Changes:**
- Add AbortController with 30s timeout to `fetchJSON()`
- Existing `askStream` already accepts a signal parameter

#### WB-4: Optimize Admin Stats Query
**Goal:** Replace expensive 10,000-row conversation list with COUNT query.
**Files:** `api/admin.py`, `stores/conversation.py`
**Changes:**
- Add `count_conversations()` method to ConversationStore
- Use `SELECT COUNT(*)` instead of loading all rows
- Replace `len(conversations)` with direct count in admin endpoint

## Implementation Order

```
WB-1: Async wrapping (highest impact for Tailscale perf)
WB-2: LLM timeouts (prevents hung requests)
WB-3: Frontend timeouts (user experience)
WB-4: Admin stats optimization (removes worst query)
WA-1: Note parsing tests
WA-2: Chunking tests
WA-3: Hybrid search RRF tests
WA-4: Reranker fallback tests
WA-5: API latency benchmarks
```

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| **Rewriting existing good tests** | task_aggregator, event_parser, stores tests are already solid |
| **Real LLM integration tests** | Require API keys, non-deterministic, expensive |
| **uvicorn multi-worker** | Single-worker is fine once blocking ops are wrapped in threads |
| **Auth/Passkey tests** | Separate concern, not causing current regressions |
| **Knowledge graph tests** | Phase 9, not built yet |

## Testing

**Automated:** All new tests run with `uv run pytest tests/ -q`
**Manual QA:** After performance fixes, test from phone over Tailscale — dashboard should load within 3s

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **`asyncio.to_thread()` over multi-worker** | Simpler, no shared state concerns, solves the blocking issue directly |
| **30s frontend timeout** | Matches typical mobile patience; long enough for LLM streaming to start |
| **60s LLM timeout** | Long enough for complex reranking, short enough to fail fast on outages |
| **COUNT instead of len(list)** | O(1) vs O(N) for the admin stats endpoint |
| **Real business logic tests over mocks** | Tests should catch regressions, not just pass |
