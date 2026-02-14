# Feature: Server Performance Hardening & Always-On Reliability

**Date:** 2026-02-14
**Branch:** main

## Summary

Fixed the root cause of intermittent phone/Tailscale failures (Mac Studio sleeping 151+ times since boot) and hardened the server for reliable remote access. Wrapped all blocking I/O with `asyncio.to_thread()`, added LLM/frontend timeouts, GZip compression, and functional test coverage for the critical RAG pipeline.

## Problem / Motivation

SecondBrain was unreliable when accessed from a phone over Tailscale. Two root causes:

1. **Mac Studio sleep cycles:** `sleep=1` (1 minute idle) caused the Mac to enter a constant sleep/DarkWake loop. DarkWake only handles TCPKeepAlive — user processes (uvicorn, Next.js) were suspended. The phone would hit a sleeping machine and get no response.

2. **Blocking async handlers:** All FastAPI async endpoints called synchronous blocking I/O (retrieval, reranking, LLM calls) directly. One slow Anthropic API call blocked every concurrent request. Combined with no timeouts on LLM clients and no frontend fetch timeouts, a single slow request could hang the entire app indefinitely.

Additionally, the backend API had no launchd service — it ran manually and died silently without restart.

## Solution

**Infrastructure:**
- Installed `com.secondbrain.api.plist` as a launchd service wrapping uvicorn with `caffeinate -ims` to prevent Mac sleep while the API runs
- Added GZip middleware to FastAPI (`minimum_size=500`) for ~70-80% compression of JSON over Tailscale

**Backend performance:**
- Wrapped all blocking I/O in `asyncio.to_thread()`: retrieval, reranking, link expansion, answer generation, briefing assembly, event parsing, task aggregation
- Added 60s timeout to both Anthropic and OpenAI client constructors (reranker + answerer)
- Replaced `list_conversations()` with `count_conversations()` in admin stats (eliminated expensive 10K-row subquery)

**Frontend:**
- Added 30s AbortController timeout to `fetchJSON()` helper
- Changed ConnectionMonitor heartbeat from `fetch("/")` (frontend only) to `fetch("/api/v1/health")` (detects backend failures)

**Test coverage:**
- Added functional tests for note parsing, chunking, hybrid RRF scoring, reranker fallback chain, and API latency benchmarks (5 new test files, ~200 new tests)

## Files Modified

**Infrastructure:**
- `com.secondbrain.api.plist` — Added `caffeinate -ims` wrapper

**Backend (async + timeouts):**
- `src/secondbrain/api/ask.py` — `asyncio.to_thread()` on retrieve, rerank, expand, answer
- `src/secondbrain/api/briefing.py` — `asyncio.to_thread()` on briefing assembly
- `src/secondbrain/api/events.py` — `asyncio.to_thread()` on event parsing
- `src/secondbrain/api/tasks.py` — `asyncio.to_thread()` on task aggregation
- `src/secondbrain/api/admin.py` — `count_conversations()` instead of full list
- `src/secondbrain/retrieval/reranker.py` — 60s timeout on LLM clients
- `src/secondbrain/synthesis/answerer.py` — 60s timeout on LLM clients
- `src/secondbrain/stores/conversation.py` — Added `count_conversations()` method
- `src/secondbrain/main.py` — Added GZipMiddleware

**Frontend:**
- `frontend/src/lib/api.ts` — 30s AbortController timeout in `fetchJSON()`
- `frontend/src/components/ConnectionMonitor.tsx` — Health check targets backend API

**Tests:**
- `tests/test_parser.py` — Note parsing functional tests
- `tests/test_chunker.py` — Chunking pipeline functional tests
- `tests/test_hybrid_rrf.py` — RRF formula and ranking tests
- `tests/test_reranker_logic.py` — Score parsing fallback chain tests
- `tests/test_api_latency.py` — API endpoint latency benchmarks
- `tests/test_admin_api.py` — Updated mocks for new dependency

**Docs:**
- `docs/features/functional-tests-performance.md` — Feature spec
- `docs/features/PROMPT-always-on-reliability.md` — Implementation prompt
- `docs/features/COORD-server-perf-and-always-on.md` — Cross-agent coordination

## Key Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| `caffeinate -ims` in plist vs `pmset -a sleep 0` | Scoped to API process — no global system changes, no sudo. Mac can sleep if service is unloaded. |
| Single uvicorn worker (no `--workers 2`) | With `asyncio.to_thread()`, one worker handles concurrency fine. Multiple workers complicate `lru_cache` singletons and SQLite connections. |
| `answer_stream()` NOT wrapped in `to_thread` | Sync iterator → async generator requires a queue pattern. Blocking time per token is small. Acceptable for single-user. |
| 60s LLM timeout, 30s frontend timeout | LLM calls legitimately take 10-30s. Frontend timeout is shorter to fail fast for the user. |
| `fetchJSON` timeout doesn't apply to `askStream` | Streaming responses are expected to be long-lived. The caller can pass their own AbortSignal. |

## Patterns Established

- **All new async FastAPI handlers wrapping sync I/O must use `asyncio.to_thread()`** — this is now the standard pattern. See `ask.py` for the canonical example.
- **LLM clients must have timeouts** — both Anthropic and OpenAI clients use `timeout=60.0` in their constructors.
- **Frontend API calls go through `fetchJSON()`** with built-in timeout — don't call `fetch()` directly for JSON endpoints.
- **ConnectionMonitor checks `/api/v1/health`** not `/` — always detect real backend state.
- **Launchd plists use `caffeinate` wrapping** for services that need the Mac awake.

## Testing

- 412 tests pass (5 new test files, ~200 new tests)
- Lint, format, mypy all clean
- Manual: verify dashboard loads on phone over Tailscale, kill API and confirm ConnectionMonitor overlay appears, let Mac idle 10+ minutes and confirm still responsive

## Future Considerations

- `answer_stream()` sync iterator still blocks event loop during token generation — needs queue pattern for true concurrent streaming (only matters if multiple users stream simultaneously)
- `deleteConversation` and `askStream` initial fetch don't go through `fetchJSON` timeout — minor gap
- `datetime.utcnow()` deprecation warnings in `conversation.py` (pre-existing)
- Bundle size is ~980KB uncompressed — consider code splitting for Insights/Admin pages if it grows further
