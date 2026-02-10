# Feature: LLM Cost Tracking + Admin Dashboard

**Phase:** 6
**Status:** Complete

## Goal

Track input/output tokens and cost for every LLM API call. Surface metrics in a new Admin dashboard page showing cost by provider, usage type, time period, and system stats.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage | SQLite `usage.db` (WAL, busy_timeout, reconnect) | Consistent with all other stores. SQL aggregation is perfect for time-range queries. |
| Instrumentation | Inline at each call site | Only 3 files have LLM calls. Inline is more readable than a callback/middleware abstraction. |
| Cost calculation | Pre-calculated at write time | Stored as `cost_usd` column. Avoids re-computing on every read. Pricing dict is easy to update. |
| Streaming tokens | Anthropic: `stream.get_final_message().usage`; OpenAI: `stream_options={"include_usage": True}` | Both SDKs support post-stream usage extraction. |
| Chart library | CSS-only bar chart (divs + Tailwind) | No heavy dependency. Simple stacked bars sufficient for daily cost view. |
| Ollama tracking | Log calls with `cost_usd=0` | Still track call counts/tokens for completeness, but $0 cost. |

## Pricing Reference

| Provider / Model | Input $/MTok | Output $/MTok |
|-----------------|-------------|--------------|
| Anthropic Haiku 4.5 | $1.00 | $5.00 |
| Anthropic Sonnet 4.5 | $3.00 | $15.00 |
| OpenAI gpt-4o-mini | $0.15 | $0.60 |
| Ollama (any) | $0.00 | $0.00 |

## Components

### Backend
- `src/secondbrain/stores/usage.py` — UsageStore with `log_usage`, `get_summary`, `get_daily_costs`, `get_recent`; `calculate_cost` pricing helper
- `src/secondbrain/api/admin.py` — 3 endpoints: `GET /admin/costs`, `GET /admin/costs/daily`, `GET /admin/stats`
- Instrumented: `llm_client.py`, `reranker.py`, `answerer.py`

### Frontend
- `frontend/src/components/admin/AdminDashboard.tsx` — Dashboard with stat cards, provider/usage breakdowns, daily cost chart
- `frontend/src/app/(dashboard)/admin/page.tsx` — Route page
- Sidebar nav item under Tools section

### Tests
- `tests/test_usage_store.py` — 13 tests (pricing, store CRUD, aggregation, reconnect)
- `tests/test_admin_api.py` — 7 tests (endpoint response shapes with mocked dependencies)
