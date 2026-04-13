# TRACE-1: OpenLLMetry Auto-Instrumentation + JSONL File Export

> **Status:** Approved
> **Ticket:** TRACE-1
> **Date:** 2026-04-09
> **Estimated effort:** 1-2 days

## Goal

Add OpenTelemetry tracing to SecondBrain's LLM calls using Traceloop's OpenLLMetry SDK, exporting spans as JSONL files for future downstream eval tooling ingestion. Zero cost, no hosted services, no changes to LLM call sites.

## Motivation

SecondBrain has had real LLM reliability issues (Gemma 4 model swap breakage, $300/month hash mismatch bug). Diagnosing these requires manual investigation. With OTel tracing:

1. Traces capture what each LLM call received and produced (full input/output)
2. downstream eval tooling (future) analyzes traces to identify behavioral contracts and risks
3. downstream eval tooling generates pytest evals that codify "this should work"
4. Model/prompt changes are caught by running those evals

This complements the existing UsageStore (cost tracking, anomaly detection, admin dashboard) — different purpose, independent systems, no shared state.

## Approach

**Approach A (selected): `traceloop-sdk`** — One package, one init call. Auto-discovers and instruments all OpenAI + Anthropic SDK clients via monkey-patching. Ollama calls go through OpenAI SDK, so they're captured too.

Rejected alternatives:
- **Individual OTel instrumentations** — Same underlying code as traceloop-sdk but more boilerplate, manual instrumentor management. No meaningful benefit for a single-user system.
- **Manual spans** — Touches every call site, defeats zero-change goal, maintenance burden.

## Architecture

### New File: `src/secondbrain/tracing.py` (~50 lines)

**`FileSpanExporter(SpanExporter)`:**
- Writes spans as JSONL, one file per UTC day: `data/traces/YYYY-MM-DD.jsonl`
- Each line is a JSON object from `span.to_json()` (OTel SDK built-in serialization)
- Creates `data/traces/` directory on first use (`mkdir -p` equivalent)
- Returns `SpanExportResult.SUCCESS` / `FAILURE` with logged exceptions
- `shutdown()` is a no-op (file handles are opened/closed per export batch)

**`init_tracing(settings)`:**
- No-op if `settings.tracing_enabled is False`
- Creates `FileSpanExporter` with path from `settings.traces_path`
- Calls `Traceloop.init(exporter=exporter)` — uses `BatchSpanProcessor` by default
- Logs startup message confirming tracing is active and output path

### Configuration: `src/secondbrain/config.py`

Two new fields in the Settings class:

```python
tracing_enabled: bool = False    # Opt-in, off by default
```

Environment variable: `SECONDBRAIN_TRACING_ENABLED=true`

Traces directory is derived from `data_path`: `Path(settings.data_path) / "traces"`. No separate config field needed — follows the same pattern as other data storage.

Off by default for safety. Brent's instance will have it enabled in `.env`.

### Integration Points

Three one-line `init_tracing(settings)` calls:

1. **`src/secondbrain/main.py`** — FastAPI app startup (before any LLM clients are created)
2. **`src/secondbrain/scripts/inbox_processor.py`** — Script entry point
3. **`src/secondbrain/scripts/daily_sync.py`** — Script entry point

Must run before LLM SDK clients are instantiated, since Traceloop patches at init time.

### LLM Call Sites Covered (zero changes needed)

| # | Component | File | What It Does |
|---|-----------|------|--------------|
| 1 | Answerer | `synthesis/answerer.py` | Answer generation (sync + streaming) |
| 2 | Reranker | `retrieval/reranker.py` | Relevance scoring |
| 3 | Inbox Processor | `scripts/inbox_processor.py` | Segmentation + classification |
| 4 | Metadata Extractor | `extraction/extractor.py` | Entity/date/action extraction |

OpenAI embedding calls (when using OpenAI embeddings) also produce spans. All Ollama calls go through the OpenAI SDK with a custom `base_url`, so they're instrumented too.

### Dependency

One new package in `pyproject.toml`:

```
traceloop-sdk >= 0.53.0
```

Transitive deps: `opentelemetry-sdk`, `opentelemetry-api`, `opentelemetry-instrumentation-openai`, `opentelemetry-instrumentation-anthropic`, and OTel core packages.

No new infrastructure — no Docker, no collector, no hosted service.

## Trace Output

**Format:** One JSONL file per UTC day (`data/traces/2026-04-09.jsonl`). Each line contains:
- Span name, trace/span IDs, timestamps (nanosecond precision)
- `llm.model_name`, `llm.token_count.prompt`, `llm.token_count.completion`
- `input.value` (prompt), `output.value` (response)
- `status.status_code`, `openinference.span.kind`

**Size:** ~2-5KB per span, ~50 spans/day = ~150KB/day, ~4.5MB/month.

**Retention:** No auto-deletion. Files accumulate as durable artifacts. Manual cleanup if needed. Future: TTL system or database migration.

**Privacy:** Input/output values contain vault content. Acceptable — traces stay local in `data/traces/` (already gitignored under `data/`), same privacy posture as the vault. downstream eval tooling runs locally.

## Relationship to UsageStore

| System | Purpose | Storage | Consumer |
|--------|---------|---------|----------|
| **UsageStore** (existing) | Cost tracking, anomaly detection, admin dashboard | `data/usage.db` (SQLite) | Admin UI, pricing guardrails |
| **OTel Traces** (this spec) | Full LLM call traces with inputs/outputs | `data/traces/*.jsonl` | downstream eval tooling |

Independent systems: no shared state, each hooks into LLM calls independently (UsageStore via explicit `_log_usage()` calls, OTel via SDK monkey-patching). Disabling one has no effect on the other.

## Testing

**Unit tests:**
- `FileSpanExporter.export()` writes valid JSONL with one line per span
- `FileSpanExporter` creates date-stamped files correctly (`YYYY-MM-DD.jsonl`)
- `init_tracing()` is a no-op when `tracing_enabled=False`
- `FileSpanExporter` handles write errors gracefully (returns `FAILURE`, logs exception)

**Integration test:**
- Enable tracing, make a mock OpenAI SDK call, verify `.jsonl` file appears with expected span attributes

No changes to existing tests. Tracing is opt-in and independent.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Traceloop monkey-patching breaks on SDK upgrade | Medium — tracing stops, app unaffected | `tracing_enabled=False` kill switch. Pin traceloop-sdk version. |
| Trace files grow unbounded | Low — ~4.5MB/month | Manual cleanup now. TTL/DB later. |
| `span.to_json()` format doesn't match downstream eval tooling expectations | Medium | Verify format during implementation. Thin adapter if needed. |
| Traceloop SDK phones home | Low | No `TRACELOOP_API_KEY` set, custom exporter overrides default. |

## Not in Scope

- No Langfuse or hosted platform (TRACE-2)
- No manual parent spans or trace hierarchy
- No changes to UsageStore or admin dashboard
- No automatic trace cleanup or rotation
- No downstream eval tooling integration in CI
- No trace viewer UI in SecondBrain frontend

## Future (TRACE-2/3)

When upgrading to Langfuse: add the platform's OTel exporter alongside `FileSpanExporter` (dual-write). JSONL files continue for downstream eval tooling. `BatchSpanProcessor` is already the right foundation for network exporters.
