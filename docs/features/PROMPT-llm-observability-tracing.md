# Implementation Prompt: LLM Observability & Tracing

> **Feature spec:** `docs/features/llm-observability-tracing.md`
> **Commit workflow:** write code → `/test-generation` → `code-simplifier` → commit
> **Do NOT implement:** WI 7 (Evals) — deferred to separate epic

## Context

Read the feature spec first: `docs/features/llm-observability-tracing.md`. It explains the problem (invisible $300/month LLM cost bug), the architecture decision (extend existing SQLite + Next.js, not LangSmith), and all 6 work items.

The codebase has 4 LLM call sites with 3 different client patterns. This implementation adds latency tracking, trace correlation, error/fallback visibility, anomaly detection, and an enhanced admin dashboard.

---

## Implementation Order

Do these in sequence. Each builds on the prior.

### Step 1: Schema Migration + Pricing Guardrails (WI 1 + WI 3)

**File: `src/secondbrain/stores/usage.py`**

1. Add 4 new columns to the `llm_usage` table. In `_init_schema()`, after the existing `CREATE TABLE IF NOT EXISTS`, add column migration:

```python
# In _init_schema(), after CREATE TABLE and CREATE INDEX statements:
# Migrate: add new columns if they don't exist
for col, sql in [
    ("trace_id", "ALTER TABLE llm_usage ADD COLUMN trace_id TEXT"),
    ("latency_ms", "ALTER TABLE llm_usage ADD COLUMN latency_ms REAL"),
    ("status", "ALTER TABLE llm_usage ADD COLUMN status TEXT DEFAULT 'ok'"),
    ("error_message", "ALTER TABLE llm_usage ADD COLUMN error_message TEXT"),
]:
    try:
        self.conn.execute(sql)
    except sqlite3.OperationalError:
        pass  # Column already exists
self.conn.executescript("""
    CREATE INDEX IF NOT EXISTS idx_usage_trace ON llm_usage(trace_id);
    CREATE INDEX IF NOT EXISTS idx_usage_status ON llm_usage(status);
""")
```

2. Update `log_usage()` signature to accept the new fields:

```python
def log_usage(
    self,
    provider: str,
    model: str,
    usage_type: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    conversation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,       # NEW
    latency_ms: float | None = None,    # NEW
    status: str = "ok",                 # NEW: "ok", "error", "fallback", "timeout"
    error_message: str | None = None,   # NEW
) -> None:
```

Update the INSERT SQL to include the 4 new columns and their parameter values. The `params` tuple and SQL column list both need updating.

3. Add warning to `calculate_cost()` for unknown paid models:

```python
def calculate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    if provider == "ollama":
        return 0.0
    provider_pricing = PRICING.get(provider, {})
    rates = provider_pricing.get(model)
    if not rates:
        logger.warning(
            "Unknown model '%s/%s' — cost recorded as $0.00. "
            "Update PRICING dict in stores/usage.py.",
            provider, model,
        )
        return 0.0
    input_rate, output_rate = rates
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
```

4. Verify pricing values are current (check Anthropic/OpenAI pricing pages):
   - `claude-haiku-4-5`: ($1.00, $5.00) per MTok
   - `claude-sonnet-4-5`: ($3.00, $15.00) per MTok
   - `gpt-4o-mini`: ($0.15, $0.60) per MTok

5. Add new query methods for traces:

```python
def get_traces(
    self,
    limit: int = 50,
    usage_type: str | None = None,
    status: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """Get recent individual usage entries with full trace data."""
    # Build WHERE clause from filters
    # SELECT all columns including trace_id, latency_ms, status, error_message
    # ORDER BY id DESC, LIMIT ?

def get_trace_group(self, trace_id: str) -> list[dict[str, Any]]:
    """Get all calls sharing a trace_id, ordered by timestamp."""
    # SELECT * FROM llm_usage WHERE trace_id = ? ORDER BY timestamp ASC

def get_anomalies(self) -> list[dict[str, Any]]:
    """Check for anomalous usage patterns. Returns list of anomaly dicts."""
    # See WI 4 below for logic
```

---

### Step 2: Instrument All Call Sites (WI 2)

This is the bulk of the work. Each call site needs: timing, error capture, trace_id, and status logging.

**Key architecture constraint:** Reranker and Answerer are **singletons** (created via `@lru_cache` in `dependencies.py`). Therefore `trace_id` must be passed **per-call** as a parameter, not via the constructor.

#### 2a. Update `_log_usage()` in all 3 components

Each component (Answerer, Reranker, LLMClient) has its own `_log_usage()` method. Update all 3 to accept and pass through the new fields:

```python
def _log_usage(
    self,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    trace_id: str | None = None,
    latency_ms: float | None = None,
    status: str = "ok",
    error_message: str | None = None,
) -> None:
    if self._usage_store:
        from secondbrain.stores.usage import calculate_cost
        cost = calculate_cost(provider, model, input_tokens, output_tokens)
        self._usage_store.log_usage(
            provider, model, "<usage_type>", input_tokens, output_tokens, cost,
            trace_id=trace_id, latency_ms=latency_ms, status=status,
            error_message=error_message,
        )
```

Where `<usage_type>` is `"chat_answer"` for Answerer, `"chat_rerank"` for Reranker, `self._usage_type` for LLMClient.

#### 2b. Instrument Reranker (`src/secondbrain/retrieval/reranker.py`)

**Change `rerank()` signature** to accept `trace_id`:
```python
def rerank(
    self,
    query: str,
    candidates: list[RetrievalCandidate],
    top_n: int = 5,
    trace_id: str | None = None,  # NEW
) -> tuple[list[RankedCandidate], RetrievalLabel]:
```

**Change `_score_candidates_batch()` signature** to accept `trace_id`:
```python
def _score_candidates_batch(
    self, query: str, candidates: list[RetrievalCandidate], trace_id: str | None = None,
) -> list[float]:
```

**Wrap the LLM call** in `_score_candidates_batch()` with timing + error capture:

```python
import time

start = time.perf_counter()
status = "ok"
error_msg = None
input_tokens = 0
output_tokens = 0
provider_name = ""

try:
    if self.provider == "anthropic":
        response = self.anthropic_client.messages.create(...)
        content = response.content[0].text
        provider_name = "anthropic"
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
    else:
        oai_response = self.openai_client.chat.completions.create(...)
        content = oai_response.choices[0].message.content or "[]"
        provider_name = "ollama" if self.base_url else "openai"
        if oai_response.usage:
            input_tokens = oai_response.usage.prompt_tokens
            output_tokens = oai_response.usage.completion_tokens

    # Parse scores (existing logic)
    scores = json.loads(content)
    if isinstance(scores, list) and len(scores) == len(candidates):
        return [float(s) for s in scores]
    # ... existing fallback parsing ...
    # If parsing fails, use similarity scores
    status = "fallback"
    return [c.similarity_score * 10 for c in candidates]

except Exception as e:
    logger.warning("Batch reranking error: %s", e)
    status = "fallback"
    error_msg = str(e)[:500]
    return [c.similarity_score * 10 for c in candidates]
finally:
    latency_ms = (time.perf_counter() - start) * 1000
    if input_tokens or status != "ok":
        self._log_usage(
            provider_name or self.provider, self.model,
            input_tokens, output_tokens,
            trace_id=trace_id, latency_ms=latency_ms,
            status=status, error_message=error_msg,
        )
```

**Critical:** When `_score_candidates_batch` catches an exception and falls back to similarity scores, log with `status="fallback"`. Currently this is invisible.

#### 2c. Instrument Answerer (`src/secondbrain/synthesis/answerer.py`)

**Change `answer()` signature:**
```python
def answer(
    self,
    query: str,
    ranked_candidates: list[RankedCandidate],
    retrieval_label: RetrievalLabel,
    conversation_history: list[ConversationMessage] | None = None,
    linked_context: list[LinkedContext] | None = None,
    trace_id: str | None = None,  # NEW
) -> str:
```

**Change `answer_stream()` signature** the same way.

**Wrap both methods** with timing + error capture (same pattern as reranker). The `answer()` method:

```python
import time

# Handle no results case (existing — no LLM call, no logging needed)
if retrieval_label == RetrievalLabel.NO_RESULTS or not ranked_candidates:
    return self.NO_RESULTS_RESPONSE

context = self._build_context(ranked_candidates, linked_context)

start = time.perf_counter()
status = "ok"
error_msg = None
try:
    if self.provider == "anthropic":
        # ... existing Anthropic call ...
        response = self.anthropic_client.messages.create(...)
        self._log_usage(
            "anthropic", self.model,
            response.usage.input_tokens, response.usage.output_tokens,
            trace_id=trace_id,
            latency_ms=(time.perf_counter() - start) * 1000,
        )
        return response.content[0].text
    else:
        # ... existing OpenAI/Ollama call ...
        oai_response = self.openai_client.chat.completions.create(...)
        if oai_response.usage:
            provider_name = "ollama" if self.base_url else "openai"
            self._log_usage(
                provider_name, self.model,
                oai_response.usage.prompt_tokens, oai_response.usage.completion_tokens,
                trace_id=trace_id,
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        return oai_response.choices[0].message.content or ""
except Exception as e:
    latency_ms = (time.perf_counter() - start) * 1000
    self._log_usage(
        self.provider, self.model, 0, 0,
        trace_id=trace_id, latency_ms=latency_ms,
        status="error", error_message=str(e)[:500],
    )
    raise
```

For `answer_stream()`: measure latency from start to stream completion (when `get_final_message()` returns or final chunk arrives). Log usage in the same `finally` block or after stream completes.

#### 2d. Instrument LLMClient (`src/secondbrain/scripts/llm_client.py`)

**Change `chat()` signature:**
```python
def chat(self, system_prompt: str, user_prompt: str, trace_id: str | None = None) -> str:
```

**Change `chat_json()` to pass through:**
```python
def chat_json(self, system_prompt: str, user_prompt: str, trace_id: str | None = None) -> dict[str, Any]:
    raw = self.chat(system_prompt, user_prompt, trace_id=trace_id)
    # ... existing JSON parsing ...
```

**Critical change: Log EACH provider attempt separately.** Currently when Anthropic fails and Ollama succeeds, only the Ollama success is logged. The implementation must log the Anthropic failure too:

```python
# Try Anthropic first
if self.anthropic_client:
    start = time.perf_counter()
    try:
        response = self.anthropic_client.messages.create(...)
        content = response.content[0].text
        self._log_usage(
            "anthropic", self._settings.inbox_model,
            response.usage.input_tokens, response.usage.output_tokens,
            trace_id=trace_id,
            latency_ms=(time.perf_counter() - start) * 1000,
        )
        return content
    except Exception:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.warning("Anthropic failed, trying Ollama fallback...", exc_info=True)
        # LOG THE FAILURE
        self._log_usage(
            "anthropic", self._settings.inbox_model, 0, 0,
            trace_id=trace_id, latency_ms=latency_ms,
            status="error", error_message="Failed, falling back to Ollama",
        )

# Try Ollama (same pattern — log failure if it fails)
# Try OpenAI (same pattern)
```

Update `_log_usage()` on LLMClient to accept the new fields (same as 2a pattern).

#### 2e. Thread trace_id from API endpoint (`src/secondbrain/api/ask.py`)

**In both `ask()` and `ask_stream()`, generate a trace_id and pass it through:**

```python
import uuid

@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, ...):
    start_time = time.time()
    trace_id = uuid.uuid4().hex  # NEW — unique per request

    # ... existing provider selection ...

    # Pass trace_id to reranker
    ranked_candidates, retrieval_label = await asyncio.to_thread(
        reranker.rerank, request.query, candidates, request.top_n,
        trace_id,  # NEW positional arg
    )

    # ... existing link expansion ...

    # Pass trace_id to answerer
    answer = await asyncio.to_thread(
        answerer.answer,
        request.query, ranked_candidates, retrieval_label,
        history, linked_context,
        trace_id,  # NEW — pass as keyword to avoid positional confusion
    )

    # ... rest of endpoint unchanged ...
```

Do the same for `ask_stream()`. For the streaming path, `answerer.answer_stream()` is called inline (not via `asyncio.to_thread`), so pass `trace_id` directly as a keyword argument.

**For background processes** (`daily_sync.py`, `inbox_processor.py`): generate a trace_id per file/note being processed. In `daily_sync.py:extract_metadata()`:

```python
import uuid

for path in stale_paths:
    trace_id = uuid.uuid4().hex
    try:
        note = connector.read_note(Path(path))
        metadata = extractor.extract(note, trace_id=trace_id)  # thread through
        # ...
```

This requires updating `MetadataExtractor.extract()` and `LLMClient.chat()` / `chat_json()` to accept and pass `trace_id`. The extractor calls `self.llm_client.chat_json()` (line 154 of `extractor.py`), so add `trace_id` param to `extract()` and pass it through.

Similarly for `inbox_processor.py`: generate trace_id per inbox file in `_process_single_file()` and pass it through `_segment_content()` and `_classify_with_retry()` to the `llm.chat()` / `llm.chat_json()` calls.

---

### Step 3: Anomaly Detection (WI 4)

**File: `src/secondbrain/stores/usage.py`**

Add `get_anomalies()` method:

```python
def get_anomalies(self) -> list[dict[str, Any]]:
    """Check for anomalous usage patterns."""
    anomalies: list[dict[str, Any]] = []

    # 1. Cost spike: today > 3x 7-day daily average
    sql = """
        SELECT
            COALESCE(SUM(CASE WHEN DATE(timestamp) = DATE('now') THEN cost_usd ELSE 0 END), 0) as today_cost,
            COALESCE(AVG(daily_cost), 0) as avg_daily_cost
        FROM (
            SELECT DATE(timestamp) as d, SUM(cost_usd) as daily_cost
            FROM llm_usage
            WHERE DATE(timestamp) >= DATE('now', '-7 days')
              AND DATE(timestamp) < DATE('now')
            GROUP BY DATE(timestamp)
        )
    """
    # If today_cost > 3 * avg_daily_cost AND avg_daily_cost > 0 AND at least 3 days of data:
    # append {"type": "cost_spike", "severity": "critical", "message": "...", "today": ..., "average": ...}

    # 2. Call count spike per usage_type: today > 3x 7-day average
    sql2 = """
        SELECT usage_type,
            SUM(CASE WHEN DATE(timestamp) = DATE('now') THEN 1 ELSE 0 END) as today_calls,
            -- 7-day daily average for this usage_type
            ...
        FROM llm_usage
        WHERE DATE(timestamp) >= DATE('now', '-7 days')
        GROUP BY usage_type
    """
    # For each usage_type: if today_calls > 3 * avg_calls: append anomaly

    # 3. High error rate: >20% of calls in last hour have status != 'ok'
    sql3 = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) as errors
        FROM llm_usage
        WHERE timestamp >= datetime('now', '-1 hour')
    """
    # If errors/total > 0.20 AND total >= 5: append anomaly

    # 4. High fallback rate: >50% of reranker calls falling back
    sql4 = """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'fallback' THEN 1 ELSE 0 END) as fallbacks
        FROM llm_usage
        WHERE usage_type = 'chat_rerank'
          AND DATE(timestamp) = DATE('now')
    """
    # If fallbacks/total > 0.50 AND total >= 3: append anomaly

    return anomalies
```

Guard against insufficient data: require at least 3 days of historical data and minimum call counts before triggering anomalies to avoid false positives.

---

### Step 4: Backend API Endpoints (WI 5 backend)

**File: `src/secondbrain/api/admin.py`**

Add 2 new endpoints:

```python
@router.get("/traces")
async def get_traces(
    usage_store: Annotated[UsageStore, Depends(get_usage_store)],
    limit: int = Query(default=50, ge=1, le=200),
    usage_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Get recent LLM call traces with full details."""
    return usage_store.get_traces(
        limit=limit, usage_type=usage_type, status=status, since=since,
    )

@router.get("/traces/{trace_id}")
async def get_trace_group(
    trace_id: str,
    usage_store: Annotated[UsageStore, Depends(get_usage_store)],
) -> list[dict[str, Any]]:
    """Get all calls sharing a trace_id."""
    return usage_store.get_trace_group(trace_id)
```

**Update `get_stats()` endpoint** to include anomalies:

```python
@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(...) -> AdminStatsResponse:
    # ... existing logic ...
    anomalies = usage_store.get_anomalies()

    return AdminStatsResponse(
        # ... existing fields ...
        anomalies=anomalies,  # NEW
    )
```

**File: `src/secondbrain/models.py`**

Add new response models and update `AdminStatsResponse`:

```python
class AnomalyAlert(BaseModel):
    """An anomalous usage pattern detected."""
    type: str          # "cost_spike", "call_spike", "high_error_rate", "high_fallback_rate"
    severity: str      # "critical", "warning", "info"
    message: str       # Human-readable description
    details: dict[str, Any] = {}  # Type-specific data (today_cost, average, etc.)

class AdminStatsResponse(BaseModel):
    """System-wide admin statistics."""
    total_queries: int
    avg_latency_ms: float
    total_conversations: int
    index_file_count: int
    total_llm_calls: int
    total_llm_cost: float
    today_cost: float = 0.0
    today_calls: int = 0
    cost_alert: str | None = None
    anomalies: list[AnomalyAlert] = []  # NEW

class TraceEntry(BaseModel):
    """A single LLM call trace entry."""
    id: int
    timestamp: str
    provider: str
    model: str
    usage_type: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    trace_id: str | None = None
    latency_ms: float | None = None
    status: str = "ok"
    error_message: str | None = None
```

**File: `frontend/src/lib/types.ts`**

Add corresponding TypeScript types:

```typescript
// Add to Admin / Cost Tracking section:

export interface AnomalyAlert {
  type: string;
  severity: "critical" | "warning" | "info";
  message: string;
  details: Record<string, unknown>;
}

export interface AdminStatsResponse {
  // ... existing fields ...
  anomalies: AnomalyAlert[];  // NEW
}

export interface TraceEntry {
  id: number;
  timestamp: string;
  provider: string;
  model: string;
  usage_type: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  trace_id: string | null;
  latency_ms: number | null;
  status: "ok" | "error" | "fallback" | "timeout";
  error_message: string | null;
}
```

**File: `frontend/src/lib/api.ts`**

Add API functions:

```typescript
export async function getTraces(params?: {
  limit?: number;
  usage_type?: string;
  status?: string;
  since?: string;
}): Promise<TraceEntry[]> {
  const qs = new URLSearchParams();
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.usage_type) qs.set("usage_type", params.usage_type);
  if (params?.status) qs.set("status", params.status);
  if (params?.since) qs.set("since", params.since);
  const q = qs.toString();
  return fetchJSON(`${BASE}/admin/traces${q ? `?${q}` : ""}`);
}

export async function getTraceGroup(traceId: string): Promise<TraceEntry[]> {
  return fetchJSON(`${BASE}/admin/traces/${traceId}`);
}
```

---

### Step 5: Enhanced Admin Dashboard (WI 5 frontend)

**File: `frontend/src/components/admin/AdminDashboard.tsx`**

The existing dashboard has: period selector, stat cards, provider breakdown, usage type breakdown, and cost chart. All using CSS-based rendering (no charting library). The existing pattern uses `glass-card` divs, `StatCard` components, and `fetchJSON` for API calls.

**Add the following:**

1. **Anomaly alert banner** — Replace or augment the existing `cost_alert` banner (currently lines ~433-444 of AdminDashboard.tsx). Render each anomaly from `stats.anomalies[]` as a colored alert card:
   - `critical` → red background, alert triangle icon
   - `warning` → amber/orange background, alert triangle icon
   - `info` → blue background, info icon

2. **Traces tab** — Add a tab switcher ("Overview" | "Traces") at the top of the dashboard:
   - **Overview tab** = existing dashboard content
   - **Traces tab** = new component showing recent LLM calls

3. **Traces table** — In the Traces tab, render a filterable table:
   - Columns: Timestamp, Type, Provider, Model, Tokens (in/out), Cost, Latency, Status
   - Color-code status: green for "ok", red for "error", orange for "fallback"
   - Filter dropdowns: usage_type, status
   - Click a row to expand and show trace_id, error_message
   - If trace_id is set, show a "View Trace" link that loads all calls with that trace_id

4. **Trace group view** — When clicking "View Trace" or a trace_id link:
   - Show all calls sharing that trace_id (typically 2: rerank + answer)
   - Show total latency (sum), total cost (sum), call sequence

5. **Latency stat card** — Add a 5th stat card showing average LLM latency (from traces data) or p95 latency.

**Implementation pattern:** Follow the existing dashboard structure — use `useState` for the active tab and traces data, `useCallback` for data loading, CSS-based table rendering matching the existing provider/usage breakdown tables.

**Loading traces data:**
```typescript
const [activeTab, setActiveTab] = useState<"overview" | "traces">("overview");
const [traces, setTraces] = useState<TraceEntry[]>([]);
const [traceFilter, setTraceFilter] = useState<{ usage_type?: string; status?: string }>({});

// Load traces when tab switches to "traces"
useEffect(() => {
  if (activeTab === "traces") {
    getTraces({ limit: 100, ...traceFilter }).then(setTraces);
  }
}, [activeTab, traceFilter]);
```

---

### Step 6: Background Process Health (WI 6)

**File: `src/secondbrain/scripts/daily_sync.py`**

After each sync step completes, log a batch summary to `usage_store`. Add this to `extract_metadata()`:

```python
# After the extraction loop completes:
usage_store.log_usage(
    provider="system",
    model="batch",
    usage_type="extraction_batch",
    input_tokens=0,
    output_tokens=0,
    cost_usd=0.0,  # batch record — individual calls already tracked
    metadata={
        "extracted": extracted,
        "failed": failed,
        "skipped": len(vault_files) - extracted - failed,
        "duration_ms": int((time.time() - step_start) * 1000),
    },
)
```

The `step_start` variable already exists in `main()` — you'll need to either pass it to `extract_metadata()` or measure within the function itself.

Similarly for `process_inbox()` in `inbox_processor.py` — at the end of the function, log a batch summary:

```python
usage_store.log_usage(
    provider="system",
    model="batch",
    usage_type="inbox_batch",
    input_tokens=0,
    output_tokens=0,
    cost_usd=0.0,
    metadata={
        "processed": len([a for a in actions if not a.startswith("FAILED")]),
        "failed": len([a for a in actions if a.startswith("FAILED")]),
        "duration_ms": int((time.time() - start_time) * 1000),
    },
)
```

In the admin dashboard, show the latest batch records in a "Sync Health" section (under the existing sync status card). Query the most recent `extraction_batch` and `inbox_batch` records and display: last run time, items processed/failed, duration.

---

## Files Modified (Summary)

| File | Changes |
|------|---------|
| `src/secondbrain/stores/usage.py` | Schema migration, `log_usage()` new params, `calculate_cost()` warning, `get_traces()`, `get_trace_group()`, `get_anomalies()` |
| `src/secondbrain/retrieval/reranker.py` | `rerank()` + `_score_candidates_batch()` accept `trace_id`, timing + error logging, fallback status |
| `src/secondbrain/synthesis/answerer.py` | `answer()` + `answer_stream()` accept `trace_id`, timing + error logging |
| `src/secondbrain/scripts/llm_client.py` | `chat()` + `chat_json()` accept `trace_id`, log each provider attempt (including failures) |
| `src/secondbrain/extraction/extractor.py` | `extract()` accepts `trace_id`, passes to `llm_client.chat_json()` |
| `src/secondbrain/scripts/inbox_processor.py` | Generate `trace_id` per file, pass through segment/classify, batch health logging |
| `src/secondbrain/scripts/daily_sync.py` | Generate `trace_id` per note in extraction, batch health logging |
| `src/secondbrain/api/ask.py` | Generate `trace_id`, pass to reranker + answerer |
| `src/secondbrain/api/admin.py` | New `/traces` and `/traces/{trace_id}` endpoints, anomalies in stats |
| `src/secondbrain/models.py` | `AnomalyAlert`, `TraceEntry`, update `AdminStatsResponse` |
| `frontend/src/lib/types.ts` | `AnomalyAlert`, `TraceEntry`, update `AdminStatsResponse` |
| `frontend/src/lib/api.ts` | `getTraces()`, `getTraceGroup()` |
| `frontend/src/components/admin/AdminDashboard.tsx` | Tab switcher, anomaly alerts, traces table, trace group view |

## What's Out of Scope

- **WI 7 (Evals)** — Deferred to separate epic
- **LangSmith / OpenTelemetry** — Rejected, see spec for rationale
- **Prompt/response content storage** — Privacy concern
- **Real-time streaming dashboard** — Unnecessary for single user
- **New navigation entries** — Admin page already exists; this adds tabs within it

## Testing

After implementation, run `/test-generation` on:
- `src/secondbrain/stores/usage.py` — schema migration, `get_anomalies()`, `get_traces()`, `calculate_cost()` warning
- `src/secondbrain/retrieval/reranker.py` — fallback status logging, trace_id threading
- `src/secondbrain/synthesis/answerer.py` — error logging, trace_id threading
- `src/secondbrain/scripts/llm_client.py` — per-provider failure logging, trace_id
- `src/secondbrain/api/admin.py` — new endpoints

Key test scenarios:
1. Schema migration on existing usage.db (columns added, data preserved)
2. `calculate_cost()` logs warning for unknown model
3. Reranker fallback logs `status="fallback"` with error_message
4. LLMClient logs failed Anthropic attempt AND successful Ollama attempt (2 rows)
5. `get_anomalies()` with normal data returns empty, with spike data returns alert
6. trace_id links reranker + answerer calls for a single query
7. Answerer error logs `status="error"` with latency

## After Implementation

- Run `code-simplifier` before committing
- Restart backend: `launchctl unload ~/Library/LaunchAgents/com.secondbrain.api.plist && sleep 2 && kill -9 $(lsof -ti:8000) 2>/dev/null && launchctl load ~/Library/LaunchAgents/com.secondbrain.api.plist`
- Rebuild frontend: `cd /Users/brentrossin/SecondBrain/frontend && npm run build && launchctl unload ~/Library/LaunchAgents/com.secondbrain.ui.plist && sleep 2 && kill -9 $(lsof -ti:7860) 2>/dev/null && launchctl load ~/Library/LaunchAgents/com.secondbrain.ui.plist`
- Verify: send a chat query and check that the admin dashboard Traces tab shows 2 correlated calls (rerank + answer) with latency and trace_id
