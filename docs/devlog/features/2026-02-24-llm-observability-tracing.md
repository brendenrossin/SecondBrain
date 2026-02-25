# Feature: LLM Observability & Tracing

**Date:** 2026-02-24
**Branch:** feature/llm-observability-tracing

## Summary

Added full-stack LLM observability to SecondBrain: per-call latency tracking, trace correlation across related calls, error/fallback visibility, anomaly detection, and an enhanced admin dashboard with a Traces tab. This prevents invisible cost bugs like the $300/month metadata extraction issue that went undetected for weeks.

## Problem / Motivation

A hash mismatch bug caused ~840 unnecessary Sonnet extraction calls per day (~$300/month) that went undetected because: (1) extraction calls weren't tracked in usage.db, (2) `calculate_cost()` silently returned $0 for unknown models, (3) no anomaly detection existed, (4) no per-call latency or trace correlation was available, and (5) the reranker's silent fallback to similarity scores was completely invisible. The core question this feature answers: "What did the LLM do, how long did it take, how much did it cost, and is that normal?"

## Solution

Extended the existing UsageStore (SQLite) + admin dashboard (Next.js) rather than adding LangSmith or OpenTelemetry. This preserves the local-first, privacy-preserving architecture while giving 90% of what a dedicated tracing platform provides.

Key components:
- 4 new columns on `llm_usage` table (trace_id, latency_ms, status, error_message)
- All 4 LLM call sites instrumented (Answerer, Reranker, LLMClient, Extractor)
- LLMClient now logs every provider attempt including failures (the critical fix)
- SQL-based anomaly detection (cost spike, call spike, error rate, fallback rate)
- Traces tab in admin dashboard with filtering, expandable rows, trace group drill-down

## Files Modified

**Backend — Schema & Store:**
- `src/secondbrain/stores/usage.py` — Schema migration, updated `log_usage()`, `get_traces()`, `get_trace_group()`, `get_anomalies()`, pricing guardrails

**Backend — Instrumentation (4 call sites):**
- `src/secondbrain/synthesis/answerer.py` — `answer()` + `answer_stream()` with timing, error logging, trace_id
- `src/secondbrain/retrieval/reranker.py` — `_score_candidates_batch()` with fallback status tracking
- `src/secondbrain/scripts/llm_client.py` — Per-provider failure logging in fallback chain
- `src/secondbrain/extraction/extractor.py` — trace_id threading to `chat_json()`

**Backend — API & Models:**
- `src/secondbrain/api/ask.py` — trace_id generation, passed to reranker + answerer
- `src/secondbrain/api/admin.py` — New `/traces` and `/traces/{trace_id}` endpoints, anomalies in stats
- `src/secondbrain/models.py` — `AnomalyAlert`, `TraceEntry`, updated `AdminStatsResponse`

**Backend — Background Processes:**
- `src/secondbrain/scripts/daily_sync.py` — Per-note trace_id, extraction_batch logging
- `src/secondbrain/scripts/inbox_processor.py` — Per-file trace_id, inbox_batch logging

**Frontend:**
- `frontend/src/components/admin/AdminDashboard.tsx` — Tab switcher, anomaly banner, TracesTab component
- `frontend/src/lib/api.ts` — `getTraces()`, `getTraceGroup()`
- `frontend/src/lib/types.ts` — `AnomalyAlert`, `TraceEntry`, updated `AdminStatsResponse`

**Tests (34 new):**
- `tests/test_usage_store.py` — Schema migration, trace fields, get_traces, get_anomalies
- `tests/test_llm_client.py` — trace_id propagation, per-provider failure logging
- `tests/test_reranker_logic.py` — Fallback status, trace_id threading
- `tests/test_answerer_tracing.py` — New file: trace_id, error provider resolution
- `tests/test_admin_api.py` — Traces endpoints, anomalies in stats

## Key Decisions & Trade-offs

| Decision | Rationale |
|---|---|
| **Extend SQLite + Next.js, not LangSmith** | Privacy-first. All prompts contain personal vault content. LangSmith would send everything to the cloud. |
| **trace_id as explicit parameter, not context var** | Codebase mixes sync/async. Reranker and Answerer are singletons via `@lru_cache`. Explicit passing works everywhere. |
| **Log every provider attempt, including failures** | The $300/month bug was invisible because failed-then-retried calls weren't tracked. 2 rows per fallback is better than 1. |
| **SQL-based anomaly detection** | Data already in SQLite with indexes. SQL aggregations are fast, avoid loading all rows into Python. |
| **3x multiplier for anomaly thresholds** | Single-user daily variance is high. 2x would cause too many false positives. |
| **`_resolved_provider` property on Answerer** | Code-simplifier extracted this to deduplicate a nested ternary used 4 times across answer/answer_stream error paths. |
| **Batch health as regular usage rows** | `usage_type='extraction_batch'` with stats in metadata JSON column keeps one table, one query pattern. |

## Patterns Established

- **Tracing pattern:** Generate `trace_id = uuid.uuid4().hex` at the entry point (API endpoint or per-file in background), pass as keyword arg through the call chain. All `_log_usage()` methods accept trace_id, latency_ms, status, error_message.
- **Error logging pattern:** Wrap LLM calls in try/except, log with `status="error"` in except block, re-raise. Use `finally` block in reranker where fallback is the expected behavior.
- **Anomaly detection pattern:** SQL queries with minimum data guards (3+ days history, 5+ calls minimum) to avoid false positives with limited data.
- **Dashboard tab pattern:** `useState<Tab>` for tab switching, separate components per tab, shared anomaly banner visible on all tabs.

## Testing

- 34 new automated tests covering all critical paths
- Manual QA: sent a chat query, verified 2 correlated calls (rerank 1.4s + answer 2.0s) with shared trace_id in the Traces tab
- Inbox batch record visible in traces table
- Filters (type, status) working correctly

## Future Considerations

- **Latency/error rate charts** (p50/p95/p99 over time) — deferred from spec, raw traces provide the data
- **"Sync Health" dedicated card** — batch data shows in usage type breakdown but no dedicated widget yet
- **2 deferred anomaly types:** "extraction running when vault unchanged" (needs vault-level knowledge) and "latency regression" (info severity, low priority)
- **WI 7 (Evals)** — Deferred to separate epic. Depends on accumulated traced data.
- **Usage.db TTL** — Need retention policy to prevent unbounded growth (being scoped as next feature)
