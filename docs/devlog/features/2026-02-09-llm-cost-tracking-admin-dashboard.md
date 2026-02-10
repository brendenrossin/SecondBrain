# Feature: LLM Cost Tracking + Admin Dashboard

**Date:** 2026-02-09
**Phase:** 6

## Summary

Added end-to-end LLM cost tracking that instruments every API call (Anthropic, OpenAI, Ollama) across all three call sites, stores token counts and pre-calculated costs in a new SQLite store, and surfaces the data through three admin API endpoints and a new frontend Admin dashboard page with stat cards, provider/usage breakdowns, and a 30-day daily cost bar chart.

## Problem / Motivation

With three LLM providers (Anthropic, OpenAI, Ollama) used across inbox processing, chat reranking, and answer generation, there was no visibility into how many API calls were being made, how many tokens were consumed, or what it was costing. This made it impossible to understand spend patterns, compare provider costs, or detect unexpected usage spikes.

## Solution

Inline instrumentation at each of the 3 LLM call sites (LLMClient, LLMReranker, Answerer) that extracts token usage from API responses and logs to a new `UsageStore` (SQLite, WAL mode). Costs are pre-calculated at write time using a pricing dictionary. Three admin API endpoints aggregate the data, and a React dashboard renders it with CSS-only stacked bar charts.

## Files Modified

**New files:**
- `src/secondbrain/stores/usage.py` — UsageStore + `calculate_cost` pricing helper
- `src/secondbrain/api/admin.py` — 3 admin endpoints (costs, daily costs, stats)
- `frontend/src/components/admin/AdminDashboard.tsx` — Full dashboard component
- `frontend/src/app/(dashboard)/admin/page.tsx` — Route page
- `tests/test_usage_store.py` — 13 store/pricing tests
- `tests/test_admin_api.py` — 7 API endpoint tests
- `docs/features/cost-tracking-admin.md` — Feature spec

**Modified files:**
- `src/secondbrain/scripts/llm_client.py` — Added `usage_store` param, logging after each provider call
- `src/secondbrain/retrieval/reranker.py` — Added `usage_store` param, logging after rerank API call
- `src/secondbrain/synthesis/answerer.py` — Added `usage_store` param, logging for both streaming and non-streaming paths
- `src/secondbrain/api/dependencies.py` — Added `get_usage_store()`, wired into all reranker/answerer/llm_client factories
- `src/secondbrain/scripts/inbox_processor.py` — Creates its own UsageStore for standalone runs
- `src/secondbrain/models.py` — Added 6 Pydantic models for cost/admin responses
- `src/secondbrain/main.py` — Registered admin router
- `frontend/src/lib/types.ts` — Added TypeScript interfaces
- `frontend/src/lib/api.ts` — Added 3 API client functions
- `frontend/src/components/layout/Sidebar.tsx` — Added Admin nav item under Tools
- `docs/ROADMAP.md` — Inserted Phase 6, renumbered subsequent phases
- `CLAUDE.md` — Updated phase list

## Key Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| **Inline instrumentation over middleware/decorator** | Only 3 call sites exist. Inline is more readable and each site has different response shapes (Anthropic vs OpenAI). A generic wrapper would need type gymnastics. |
| **Pre-calculated `cost_usd` column** | Avoids re-computing costs on every read. Pricing dict is easy to update. If pricing changes, only future calls are affected (historical costs remain accurate for when they were made). |
| **Streaming token extraction** | Anthropic: `stream.get_final_message().usage` after `yield from text_stream`. OpenAI: `stream_options={"include_usage": True}` captures usage in the final chunk. Ollama: `stream_options` is skipped (may not support it) — tokens still logged if Ollama returns usage data. |
| **`from __future__ import annotations` for TYPE_CHECKING** | Used to avoid circular imports between stores/usage.py and the instrumented modules. UsageStore is only imported at type-check time. |
| **CSS-only bar chart** | No chart library dependency. Simple stacked div bars with Tailwind classes. Hover tooltips show date/cost/calls. Sufficient for daily cost visualization. |
| **FastAPI `dependency_overrides` in tests** | `patch()` doesn't work with FastAPI's `Depends()` injection. Using `app.dependency_overrides[get_usage_store] = lambda: mock` is the correct pattern. |

## Patterns Established

- **UsageStore follows the existing store pattern**: WAL mode, busy_timeout=5000, `_reconnect()` on DatabaseError, lazy `conn` property — identical to ConversationStore, MetadataStore, IndexTracker.
- **`_log_usage()` helper on instrumented classes**: Each instrumented class has a private `_log_usage()` method that guards on `self._usage_store` being non-None, imports `calculate_cost` lazily, and calls `log_usage()`. This keeps the actual call site instrumentation to 3-4 lines.
- **Admin API router under `/api/v1/admin/`**: Establishes the admin namespace for future operational endpoints.
- **`datetime.now(UTC)` over `datetime.utcnow()`**: Used the non-deprecated pattern throughout new code.

## Testing

- 13 unit tests for UsageStore: schema creation, log + get_recent, get_summary with/without date filters, get_daily_costs grouping, conversation_id tracking, reconnect resilience
- 6 pricing tests for `calculate_cost`: all providers, unknown models, Ollama-is-free
- 7 API tests with mocked dependencies: all 3 endpoints, period validation (422 for invalid), response shape assertions
- End-to-end verification: restarted backend, confirmed real usage data appears in `/admin/costs` and `/admin/stats`
- Frontend: confirmed `/admin` page returns 200, dashboard renders with real data

## Future Considerations

- **Pricing updates**: When Anthropic/OpenAI change prices, update the `PRICING` dict in `usage.py`. Historical rows keep their original costs.
- **Conversation-level cost tracking**: `conversation_id` is logged but not yet surfaced in the UI. Could show per-conversation cost in chat history.
- **Export/alerting**: No cost alerts or CSV export yet. Could add threshold notifications.
- **Retention policy**: No automatic cleanup of old usage rows. At current volume this is fine; may need a retention policy if thousands of calls/day.
