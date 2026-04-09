# Phase 9.8a — OpenLLMetry + Local File Export

> **Status:** Planned
> **Estimated effort:** 1-2 days
> **Depends on:** Phase 9.7 (RAG Quality & Performance)
> **Blocked by:** Nothing — can start as soon as 9.7 is complete

## Goal

Add OpenTelemetry tracing to SecondBrain's LLM calls using OpenLLMetry auto-instrumentation, exporting spans as JSONL files that TraceEval can ingest directly. Zero cost, no hosted services, minimal code changes.

## Motivation

SecondBrain has real LLM reliability issues (e.g., the Gemma 4 model swap causing breakage, the $300/month hash mismatch bug). Diagnosing these requires manual investigation. With tracing + TraceEval:

1. Tracing captures what each LLM call received and produced
2. TraceEval analyzes those traces to identify behavioral contracts and risks
3. TraceEval generates pytest evals that codify "this should work"
4. When you swap models or change prompts, those evals catch regressions automatically

This is the dogfooding use case — proving TraceEval works on a real project.

---

## Architecture Decision: Complementary Systems

SecondBrain has two observability systems with distinct purposes:

| System | Purpose | Storage | Consumer |
|--------|---------|---------|----------|
| **UsageStore** (existing) | Cost tracking, anomaly detection, admin dashboard | `data/usage.db` (SQLite) | Admin UI, pricing guardrails |
| **OTel Traces** (this spec) | Full LLM call traces with inputs/outputs | `data/traces/*.jsonl` | TraceEval |

These systems are independent:
- No shared state or tables
- Each hooks into LLM calls independently (UsageStore via `_log_usage()`, OTel via SDK monkey-patching)
- Disabling one has no effect on the other
- Different retention policies (UsageStore is permanent, traces can be pruned)

---

## Dependencies

### New Python Packages

```
openllmetry-sdk          # Auto-instrumentation for OpenAI + Anthropic SDKs
opentelemetry-sdk        # Core OTel SDK (transitive dep, needed directly for FileSpanExporter)
```

OpenLLMetry pulls in `opentelemetry-api` and instrumentation packages for the SDKs we use.

### No New Infrastructure

No collector, no Docker, no hosted service. Just a Python init call and a file exporter.

---

## Configuration

### New Settings (in `config.py`)

```python
tracing_enabled: bool = False    # Opt-in, off by default
traces_path: str = "data/traces" # Where JSONL files land
```

### Environment Variables

```bash
SECONDBRAIN_TRACING_ENABLED=true           # Enable OTel tracing
SECONDBRAIN_TRACES_PATH=data/traces        # Optional override
```

---

## Implementation

### New File: `src/secondbrain/tracing.py` (~40-60 lines)

The entire integration surface:

```python
"""OTel tracing initialization for TraceEval integration."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

logger = logging.getLogger(__name__)


class FileSpanExporter(SpanExporter):
    """Exports OTel spans as JSONL files, one per day."""

    def __init__(self, traces_dir: Path):
        self._traces_dir = traces_dir
        self._traces_dir.mkdir(parents=True, exist_ok=True)

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._traces_dir / f"{today}.jsonl"
        try:
            with open(path, "a") as f:
                for span in spans:
                    f.write(json.dumps(span.to_json()) + "\n")
            return SpanExportResult.SUCCESS
        except Exception:
            logger.exception("Failed to export spans to %s", path)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass


def init_tracing(settings) -> None:
    """Initialize OTel tracing if enabled. Call once at app startup."""
    if not settings.tracing_enabled:
        return

    from openllmetry.sdk import init as openllmetry_init
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    traces_dir = Path(settings.data_path) / "traces"
    exporter = FileSpanExporter(traces_dir)

    openllmetry_init(
        exporter=exporter,
        processor=SimpleSpanProcessor(exporter),
    )

    logger.info("OTel tracing enabled — writing spans to %s", traces_dir)
```

**Note:** The exact OpenLLMetry init API may differ slightly — verify against current docs during implementation. The structure above captures the intent.

### One-Line Addition to `main.py`

```python
from secondbrain.tracing import init_tracing
init_tracing(settings)
```

### Zero Changes to LLM Call Sites

OpenLLMetry patches the OpenAI and Anthropic SDK clients at import time. Existing code in Answerer, Reranker, LLMClient, and Embedder emits spans without any modification.

---

## What the Traces Contain

OpenLLMetry auto-captures per LLM call:

| Attribute | Example | TraceEval Uses It For |
|-----------|---------|----------------------|
| `openinference.span.kind` | `"LLM"` | Filtering span types |
| `llm.model_name` | `"claude-haiku-4-5"` | Model identification |
| `llm.token_count.prompt` | `1200` | Cost analysis |
| `llm.token_count.completion` | `350` | Cost analysis |
| `input.value` | `"Summarize the following..."` | Behavioral contract extraction |
| `output.value` | `"The document discusses..."` | Output pattern analysis |
| `status.status_code` | `"STATUS_CODE_OK"` | Error detection |
| Start/end timestamps | nanosecond precision | Latency analysis |

This is the exact attribute set TraceEval expects via OpenInference conventions.

### Privacy Note

`input.value` and `output.value` contain vault content (prompts include note text). Acceptable because:
- Traces stay local in `data/traces/` (already gitignored under `data/`)
- Same privacy posture as the vault itself
- TraceEval runs locally too

---

## Trace File Management

- **Format:** One JSONL file per day — `data/traces/2026-04-05.jsonl`
- **Size estimate:** ~2-5KB per span. At ~50 spans/day (20 queries + daily sync) = ~150KB/day, ~4.5MB/month
- **Retention:** Files are never auto-deleted. They're durable artifacts for TraceEval analysis and can be bulk-imported into future platforms (Langfuse, LangSmith)
- **Manual cleanup:** `rm data/traces/2026-03-*.jsonl` if needed, or future `make traces-clean`
- **`.gitignore`:** `data/` is already gitignored

---

## TraceEval Consumption

Once traces have accumulated (recommend at least 1-2 weeks of normal usage):

```bash
cd ~/TraceEval
traceeval analyze --input ~/SecondBrain/data/traces/
traceeval generate
traceeval export --output evals/
pytest evals/
```

The generated evals codify behavioral contracts observed in the traces. When SecondBrain's models or prompts change, running those evals catches regressions.

---

## LLM Call Sites Covered

OpenLLMetry auto-instruments all SDK calls. These are the 4 active call sites that will produce spans:

| # | Component | File | Usage Type | What It Does |
|---|-----------|------|------------|--------------|
| 1 | **Answerer** | `synthesis/answerer.py` | `chat_answer` | Answer generation (sync + streaming) |
| 2 | **Reranker** | `retrieval/reranker.py` | `chat_rerank` | Relevance scoring |
| 3 | **Inbox Processor** | `scripts/inbox_processor.py` | `inbox` | Segmentation + classification (2 calls per capture) |
| 4 | **Metadata Extractor** | `extraction/extractor.py` | `extraction` | Entity/date/action extraction |

Additionally, OpenAI embedding calls (when using OpenAI embeddings) will produce spans. TraceEval can filter these by `openinference.span.kind`.

---

## Testing

### Automated

- **Unit:** `FileSpanExporter.export()` writes valid JSONL with one line per span
- **Unit:** `init_tracing()` is a no-op when `tracing_enabled=False`
- **Unit:** `FileSpanExporter` creates date-stamped files correctly
- **Integration:** Make a mock LLM call with tracing enabled, verify `.jsonl` file appears with expected OpenInference attributes

### Manual QA

- Enable tracing, run a chat query, check `data/traces/` for today's file
- Verify span attributes match what TraceEval expects (model name, tokens, input/output)
- Feed the trace file to `traceeval analyze` and confirm it parses successfully
- Disable tracing, verify no spans are written and no performance impact

---

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenLLMetry monkey-patching breaks on SDK upgrade | Medium — tracing stops, SecondBrain unaffected | `tracing_enabled=False` kill switch. Pin openllmetry version. |
| Trace files grow unbounded | Low — ~4.5MB/month | Manual cleanup. Add rotation if needed. |
| OpenLLMetry captures embedding calls too | Low — extra spans | TraceEval filters by `openinference.span.kind`. |
| Span serialization performance | Very low — microseconds vs. seconds for LLM calls | No mitigation needed. |
| `span.to_json()` format doesn't match TraceEval's expected JSONL | Medium — TraceEval can't parse | Verify format during implementation. May need a thin adapter in the exporter. |

---

## What's NOT in Scope

- No Langfuse, LangSmith, or hosted platform (Phase 9.8b/c)
- No manual parent spans or trace hierarchy
- No changes to UsageStore or admin dashboard
- No automatic trace cleanup or rotation
- No TraceEval integration in CI or automated eval runs
- No trace viewer UI in SecondBrain frontend

---

## Future Evolution (9.8b/c)

When upgrading to Langfuse or another platform:

1. Add the platform's OTel exporter alongside `FileSpanExporter` (dual-write)
2. Platform provides trace viewer UI, parent/child grouping, search
3. JSONL files continue for TraceEval (or TraceEval adds a Langfuse adapter)
4. Accumulated JSONL files can be bulk-imported into the platform for historical analysis

The key invariant: **TraceEval always has access to OTel-format traces**, regardless of the tracing platform.
