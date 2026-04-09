# LLM Observability & Tracing — Full-Stack LLM Visibility

> **Status:** Planned (Phase 6.7)
> **Estimated effort:** 5-7 days
> **Depends on:** Phase 6 (LLM cost tracking — done), hash mismatch fix (done)
> **Supersedes:** Original exploration doc (2026-02-24)

## Problem

SecondBrain has 4 active LLM call sites, each making real API calls that cost money. A hash mismatch bug recently caused ~840 unnecessary Sonnet calls/day ($8–10/day, ~$300/month) that went undetected for weeks because:

1. **Extraction calls weren't tracked in usage.db** — the `LLMClient` was created without a `UsageStore`
2. **`calculate_cost()` returns $0.00 silently for unknown models** — no warning logged, no alert triggered
3. **No anomaly detection** — the admin dashboard shows raw numbers but can't flag "extraction ran 840 times today when it should run 0"
4. **No per-call latency or trace correlation** — can't tell if a slow query is the reranker (500ms) or the answerer (4500ms)
5. **No error/fallback visibility** — the reranker silently falls back to similarity scores on LLM failure with no metric on how often this happens

The core question this feature answers: **"What did the LLM do, how long did it take, how much did it cost, and is that normal?"**

---

## Corrected LLM Call Site Inventory

Every place in the codebase that makes an LLM API call (verified by reading source):

| # | Component | File | Method | Usage Type | Providers | Notes |
|---|-----------|------|--------|------------|-----------|-------|
| 1 | **Answerer** | `synthesis/answerer.py` | `answer()`, `answer_stream()` | `chat_answer` | Anthropic / OpenAI / Ollama | Creates own SDK clients. Streaming extracts tokens after completion. |
| 2 | **Reranker** | `retrieval/reranker.py` | `_score_candidates_batch()` | `chat_rerank` | Anthropic / OpenAI / Ollama | Creates own SDK clients. Silent fallback to similarity scores on error. |
| 3 | **Inbox Processor** | `scripts/inbox_processor.py` | via `LLMClient.chat()` / `chat_json()` | `inbox` | Anthropic → Ollama → OpenAI (fallback chain) | 2 LLM calls per capture: segmentation + classification. |
| 4 | **Metadata Extraction** | `extraction/extractor.py` | via `LLMClient.chat_json()` | `extraction` | Anthropic → Ollama → OpenAI (fallback chain) | 1 LLM call per stale note. Orchestrated by `daily_sync.py`. |

**NOT LLM call sites** (incorrectly included in prior doc):
- **Quick capture** (`api/capture.py`) — embedding-only, no LLM
- **Weekly review** (`scripts/weekly_review.py`) — pure template aggregation from daily notes, zero LLM calls

### Three Distinct Client Patterns

The codebase has 3 different patterns for making LLM calls. Any instrumentation must handle all 3:

1. **`LLMClient` fallback chain** (inbox, extraction) — tries Anthropic → Ollama → OpenAI. Single `chat()` method. Usage logged in `_log_usage()`.
2. **`Answerer` direct SDK calls** (chat answers) — creates its own `Anthropic` / `OpenAI` clients. Separate sync and streaming paths. Usage logged in `_log_usage()` with hardcoded `"chat_answer"`.
3. **`LLMReranker` direct SDK calls** (reranking) — creates its own `Anthropic` / `OpenAI` clients. Single batch call. Usage logged in `_log_usage()` with hardcoded `"chat_rerank"`.

---

## Solution: Extend Existing Infrastructure

### Architecture Decision: Why Not LangSmith / OpenTelemetry

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Extend UsageStore + Admin Dashboard** | Local, no new deps, privacy-preserving, builds on existing SQLite + Next.js | We build our own trace UI | **Chosen** |
| **LangSmith** | Best tracing UI, free tier, eval support | Cloud-hosted — all vault content (prompts) sent to LangSmith servers. Violates "local-first, privacy-preserving" principle. | Rejected |
| **Langfuse (self-hosted)** | Open-source LangSmith. Can run locally via Docker. | Adds Docker dependency, Postgres, and a second web UI to maintain. Overkill for single-user. | Deferred — revisit if built-in dashboard proves insufficient |
| **OpenTelemetry** | Vendor-neutral, industry standard | Needs a collector + backend (Jaeger/Zipkin). Heavy infrastructure for 1 user. | Rejected |

**Rationale:** SecondBrain is a single-user system running on one Mac Studio. The existing `UsageStore` (SQLite) + admin dashboard (Next.js) already track costs. Extending them with latency, trace IDs, error tracking, and anomaly detection gives us 90% of what LangSmith provides, with zero privacy compromise and zero new infrastructure.

If the built-in tracing proves insufficient for debugging complex issues, Langfuse (Docker, self-hosted) is the upgrade path — but we should exhaust the simple approach first.

---

## Work Items

### Work Item 1: Enhanced LLM Call Schema

**Goal:** Capture latency, trace correlation, error state, and token details for every LLM call.

**Current schema** (`llm_usage` table):
```
id, timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, conversation_id, metadata
```

**New columns:**
```sql
ALTER TABLE llm_usage ADD COLUMN trace_id TEXT;          -- Groups related calls (e.g., rerank + answer for one query)
ALTER TABLE llm_usage ADD COLUMN latency_ms REAL;        -- Wall-clock time for this specific LLM call
ALTER TABLE llm_usage ADD COLUMN status TEXT DEFAULT 'ok'; -- 'ok', 'error', 'fallback', 'timeout'
ALTER TABLE llm_usage ADD COLUMN error_message TEXT;      -- Error details when status != 'ok'
```

**New index:**
```sql
CREATE INDEX IF NOT EXISTS idx_usage_trace ON llm_usage(trace_id);
CREATE INDEX IF NOT EXISTS idx_usage_status ON llm_usage(status);
```

**Behavior:**
- `trace_id` is a UUID generated at the start of a user query (in the `/ask` endpoint) and threaded through to the reranker and answerer. For background processes (inbox, extraction), each file/note processing gets its own trace_id.
- `latency_ms` is measured by wrapping each LLM API call with `time.perf_counter()`.
- `status` captures the outcome: `ok` (success), `error` (call failed, no fallback), `fallback` (call failed, fell back to next provider or similarity scores), `timeout` (60s limit hit).
- `error_message` stores the exception message on failure.

**Files:**
- `src/secondbrain/stores/usage.py` — schema migration, updated `log_usage()` signature
- `src/secondbrain/models.py` — update Pydantic response models

**Migration strategy:** `ALTER TABLE ADD COLUMN` with defaults — no data loss, backward compatible.

---

### Work Item 2: Instrument All Call Sites

**Goal:** Every LLM call logs latency, status, and trace_id. Wrap each call with timing + error capture.

**Pattern** (pseudo-code for each call site):
```python
import time, uuid

def _call_llm_with_tracing(self, ...):
    start = time.perf_counter()
    status = "ok"
    error_msg = None
    try:
        response = self.client.messages.create(...)
        return response
    except TimeoutError:
        status = "timeout"
        error_msg = "60s timeout exceeded"
        raise
    except Exception as e:
        status = "error"
        error_msg = str(e)[:500]
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        self._log_usage(..., latency_ms=latency_ms, status=status, error_message=error_msg)
```

**Per call site:**

| Call Site | trace_id Source | Status Values | Special Handling |
|-----------|----------------|---------------|------------------|
| **Answerer.answer()** | Passed from `/ask` endpoint | `ok` / `error` / `timeout` | Log even on error |
| **Answerer.answer_stream()** | Passed from `/ask` endpoint | `ok` / `error` / `timeout` | Latency = full stream duration (first token to last) |
| **Reranker._score_candidates_batch()** | Passed from `/ask` endpoint | `ok` / `fallback` / `timeout` | Log `fallback` when returning similarity scores instead of LLM scores |
| **LLMClient.chat()** | Generated per-file in inbox/extraction | `ok` / `fallback` / `error` | Log each provider attempt separately: Anthropic (error) → Ollama (ok) = 2 rows |
| **LLMClient.chat_json()** | Inherits from `chat()` | Same as above | JSON parse failures are separate from LLM failures |

**Critical fix for LLMClient fallback chain:** Currently, when Anthropic fails and Ollama succeeds, only the successful call is logged. The failed Anthropic attempt is invisible. The instrumented version must log BOTH: the Anthropic call with `status=error` and the Ollama call with `status=ok`. This is essential for understanding fallback frequency.

**Files:**
- `src/secondbrain/synthesis/answerer.py` — wrap `answer()` and `answer_stream()`
- `src/secondbrain/retrieval/reranker.py` — wrap `_score_candidates_batch()`
- `src/secondbrain/scripts/llm_client.py` — wrap each provider attempt in `chat()`
- `src/secondbrain/api/routes.py` (or wherever `/ask` is handled) — generate trace_id, pass to reranker + answerer

---

### Work Item 3: Pricing Guardrails

**Goal:** Never silently return $0.00 for a paid API call.

**Current bug:** `calculate_cost()` returns 0.0 for any model not in the `PRICING` dict. This is exactly what happened with the extraction bug — calls were made but cost was $0.00 because the model wasn't tracked.

**Fix:**
```python
def calculate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    if provider == "ollama":
        return 0.0
    provider_pricing = PRICING.get(provider, {})
    rates = provider_pricing.get(model)
    if not rates:
        logger.warning(
            "Unknown model '%s/%s' — cost will be $0.00. "
            "Add pricing to PRICING dict in stores/usage.py",
            provider, model,
        )
        return 0.0
    input_rate, output_rate = rates
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
```

**Additionally:** Verify current pricing values are accurate:
- `claude-haiku-4-5`: $1.00 / $5.00 per MTok — **verify against Anthropic pricing page**
- `claude-sonnet-4-5`: $3.00 / $15.00 per MTok — **verify**
- `gpt-4o-mini`: $0.15 / $0.60 per MTok — **verify against OpenAI pricing page**

**Files:**
- `src/secondbrain/stores/usage.py` — add warning log, verify pricing values

---

### Work Item 4: Anomaly Detection

**Goal:** Detect and surface when LLM usage deviates from normal patterns.

**Anomalies to detect:**

| Anomaly | Detection Rule | Alert Severity |
|---------|----------------|----------------|
| **Cost spike** | Today's cost > 3x 7-day daily average | Critical |
| **Call count spike** | Today's calls for a `usage_type` > 3x its 7-day average | Critical |
| **Extraction running when vault unchanged** | `extraction` calls > 0 but no files modified since last sync | Warning |
| **High error rate** | >20% of calls in last hour have `status != 'ok'` | Warning |
| **High fallback rate** | >50% of reranker calls falling back to similarity scores | Warning |
| **Latency regression** | Average latency for a `usage_type` > 2x its 7-day average | Info |

**Implementation:**

New method on `UsageStore`:
```python
def get_anomalies(self) -> list[dict[str, Any]]:
    """Check for anomalous usage patterns. Returns list of anomaly dicts."""
```

This runs on every `/admin/stats` request (cheap — just SQL aggregations on an indexed table). Anomalies are returned in the `AdminStatsResponse` as a new `anomalies` list field.

**Files:**
- `src/secondbrain/stores/usage.py` — `get_anomalies()` method
- `src/secondbrain/api/admin.py` — include anomalies in stats response
- `src/secondbrain/models.py` — `AnomalyAlert` model, update `AdminStatsResponse`
- `frontend/src/components/admin/AdminDashboard.tsx` — render anomaly alerts

---

### Work Item 5: Trace Detail View (Admin Dashboard)

**Goal:** Add a per-call trace view to the admin dashboard so the user can drill into individual LLM calls.

**New API endpoint:**
```
GET /api/v1/admin/traces?limit=50&usage_type=&status=&since=
```

Returns recent LLM calls with all fields (timestamp, provider, model, usage_type, tokens, cost, latency, status, error_message, trace_id).

**New API endpoint:**
```
GET /api/v1/admin/traces/{trace_id}
```

Returns all calls sharing a trace_id (e.g., the reranker + answerer calls for a single user query), ordered by timestamp.

**Frontend additions:**
- **Traces tab** in admin dashboard — sortable/filterable table of recent LLM calls
- **Trace detail view** — click a trace_id to see all calls in that trace grouped together, with total latency/cost breakdown
- **Latency chart** — p50/p95/p99 latency by usage_type over time (daily granularity)
- **Error rate chart** — percentage of calls with `status != 'ok'` per day
- **Anomaly alert banner** — replaces simple cost alert with richer anomaly cards

**Files:**
- `src/secondbrain/api/admin.py` — new endpoints
- `src/secondbrain/stores/usage.py` — new query methods
- `src/secondbrain/models.py` — response models
- `frontend/src/components/admin/AdminDashboard.tsx` — new tab + charts
- `frontend/src/lib/types.ts` — TypeScript types

---

### Work Item 6: Background Process Health Metrics

**Goal:** Track extraction and inbox processing health in usage.db so it's visible in the admin dashboard.

**Current state:** `daily_sync.py` logs structured JSON events to stdout but these aren't queryable:
```python
_log_structured("extraction_complete", summary=summary, duration_ms=elapsed)
```

**Enhancement:** After each sync step completes, log a summary record to usage.db with `usage_type` suffixed with `_batch`:
- `extraction_batch` — total notes processed, failed, skipped, total duration
- `inbox_batch` — total captures processed, failed, total duration

These use the existing `metadata` JSON column to store batch-level stats:
```python
usage_store.log_usage(
    provider="system",
    model="batch",
    usage_type="extraction_batch",
    input_tokens=0,
    output_tokens=0,
    cost_usd=total_batch_cost,  # sum of individual extraction costs
    metadata={
        "extracted": 5,
        "failed": 0,
        "skipped": 30,
        "duration_ms": 12500,
    },
)
```

This makes batch health queryable alongside individual call data — no new tables needed.

**Files:**
- `src/secondbrain/scripts/daily_sync.py` — log batch summaries to usage_store
- `frontend/src/components/admin/AdminDashboard.tsx` — "Sync Health" card showing latest batch stats

---

### Work Item 7: LLM Output Evals (Future — Scope-Gated)

> **Note:** This work item is intentionally scoped as a future addition. It depends on WI 1-5 being complete and the user accumulating enough traced data to evaluate patterns. Do not implement in v1.

**Goal:** Automated quality checks on LLM outputs, using the traced data as the foundation.

**Eval Types:**

| Eval | What It Checks | Method | When to Run |
|------|----------------|--------|-------------|
| **Answer groundedness** | Does the answer only use information from provided sources? | LLM-as-judge (send answer + sources to a judge model, ask "is this grounded?") | Sampled: 10% of chat queries |
| **Extraction accuracy** | Are extracted entities/dates/actions correct? | Golden dataset: manually label 20 notes, compare LLM output | On-demand: `make eval-extraction` |
| **Reranker effectiveness** | Does reranking improve result quality vs. raw retrieval? | A/B: run queries with and without reranking, compare recall@5 | On-demand: `make eval-reranker` |
| **Inbox parsing** | Correct categorization and structure? | Golden dataset: manually label 10 inbox captures | On-demand: `make eval-inbox` |

**Architecture:** Extends the existing `src/secondbrain/eval/` harness (which currently only evaluates retrieval). The eval harness already has the pattern: YAML test cases → run → compute metrics → save report.

**NOT included:** LangSmith eval integration, automated eval pipelines, continuous eval in production. These are unnecessary for a single-user system.

---

## Implementation Order

```
WI 1 (Schema) ← WI 2 (Instrument) ← WI 3 (Pricing) can be done together as foundation
                      ↓
WI 4 (Anomaly Detection) ← depends on WI 1 for status/latency data
                      ↓
WI 5 (Dashboard) ← depends on WI 1+4 for data to display
                      ↓
WI 6 (Batch Health) ← independent, can be done in parallel with WI 4-5
                      ↓
WI 7 (Evals) ← deferred, depends on all above + accumulated data
```

**Recommended implementation sequence:**
1. **WI 1 + WI 3** together (schema + pricing guardrails) — foundation, ~1 day
2. **WI 2** (instrument all call sites) — the bulk of the work, ~2 days
3. **WI 4** (anomaly detection) — ~0.5 day
4. **WI 5** (dashboard) — ~1.5 days
5. **WI 6** (batch health) — ~0.5 day
6. **WI 7** (evals) — deferred to separate epic

---

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| **LangSmith integration** | Violates local-first privacy principle. All prompts contain personal vault content. |
| **OpenTelemetry** | Over-engineered for a single-user system. Would need collector + backend. |
| **Prompt/response content storage** | Privacy concern. Logging full prompts would store all vault content in usage.db. Token counts + latency + status are sufficient for debugging. |
| **Real-time streaming dashboard** | WebSocket push for live cost updates. Unnecessary — single user, manual refresh is fine. |
| **Automated eval pipelines** | Running evals on every query adds latency and cost. On-demand eval is sufficient. |
| **Weekly review `usage_type`** | Weekly review makes zero LLM calls (pure template aggregation). No tracking needed. |
| **External alerting (email/Slack/push)** | Dashboard alerts are sufficient for a single-user system checking the admin page. |

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Schema migration breaks existing data** | Medium — `ALTER TABLE ADD COLUMN` is safe for SQLite, but bugs in migration code could corrupt usage.db | Test migration on a copy of production usage.db before deploying |
| **Timing overhead on LLM calls** | Low — `time.perf_counter()` adds nanoseconds | No mitigation needed |
| **trace_id threading across async code** | Medium — FastAPI uses async, trace_id must be passed explicitly (no thread-local magic) | Pass trace_id as explicit parameter, not via context vars |
| **Fallback chain logging doubles row count** | Low — logging failed attempts creates more rows (e.g., Anthropic fail + Ollama success = 2 rows vs. 1 today) | Acceptable. More data is better for debugging. Filter by `status='ok'` for cost reports. |
| **Anomaly detection false positives** | Medium — early on with limited data, 7-day averages may be unstable | Use minimum threshold (e.g., at least 7 days of data before anomaly detection activates) |
| **Dashboard bundle size increase** | Low — new charts and tables | Lazy-load the traces tab. Keep chart library (already using recharts). |

---

## Testing

**Automated:**
- Unit tests for schema migration (add columns, verify defaults)
- Unit tests for `calculate_cost()` warning behavior on unknown models
- Unit tests for `get_anomalies()` with synthetic data (normal patterns, spike patterns, error patterns)
- Integration test: mock LLM call → verify usage row has latency, trace_id, status
- Integration test: LLM call timeout → verify `status='timeout'` logged
- Integration test: LLMClient fallback → verify both failed and successful calls logged

**Manual QA:**
- Run a chat query and verify trace_id links reranker + answerer calls in the traces view
- Trigger a cost anomaly (e.g., run extraction 10x) and verify the dashboard shows an alert
- Intentionally misconfigure Anthropic API key → verify error calls are logged with `status='error'`
- Run daily sync → verify batch health record appears in admin dashboard

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Extend UsageStore, not add LangSmith** | Privacy-first system. All prompts contain personal notes. SQLite + Next.js dashboard is already built and sufficient. |
| **Log failed LLM attempts (not just successful)** | The $300/month bug was invisible because failed-then-retried calls weren't tracked. Logging every attempt reveals fallback patterns and provider reliability. |
| **trace_id as explicit parameter, not context var** | The codebase mixes sync and async code. Context vars (contextvars) work for async but not for the sync `answer_stream()` generator. Explicit passing is simpler and works everywhere. |
| **Anomaly detection in SQL, not Python** | The data is already in SQLite with indexes on timestamp. SQL `GROUP BY DATE(timestamp)` aggregations are fast and avoid loading all rows into Python. |
| **No prompt/response content storage** | Even in a local system, storing all prompts means usage.db becomes a second copy of the vault. Token counts + latency + error status are sufficient for the debugging scenarios we've seen. |
| **Batch health as regular usage rows (not a separate table)** | Using `usage_type='extraction_batch'` with stats in the `metadata` JSON column keeps the schema simple. One table, one dashboard, one query pattern. |
| **3x multiplier for anomaly detection (not 2x)** | Daily variance in a single-user system is high (some days you chat a lot, some days you don't). 2x would create too many false positives. 3x catches genuine spikes while tolerating normal variation. |

---

## Appendix: Current Usage Type Taxonomy

| usage_type | Component | Frequency | Typical Cost/Call |
|------------|-----------|-----------|-------------------|
| `chat_answer` | Answerer | Per user query | ~$0.002 (Haiku) |
| `chat_rerank` | Reranker | Per user query | ~$0.001 (Haiku) |
| `inbox` | Inbox Processor | 2 calls per inbox capture (segment + classify) | ~$0.001 (Haiku) |
| `extraction` | Metadata Extractor | 1 call per stale note | ~$0.001 (Haiku) |
| `extraction_batch` | Daily Sync (new) | 1 per sync run | $0 (metadata only) |
| `inbox_batch` | Daily Sync (new) | 1 per sync run | $0 (metadata only) |

---

## Incident Reference

See `docs/devlog/errors/2026-02-24-metadata-extraction-hash-mismatch-cost-explosion.md` for the full post-mortem on the $300/month invisible cost bug that motivated this feature.
