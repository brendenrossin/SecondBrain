# TraceEval Integration

This directory tracks SecondBrain's side of the TraceEval integration — OTel instrumentation, trace export configuration, and notes on trace quality.

## What is TraceEval?

TraceEval (`~/TraceEval`) is a **trace-to-eval compiler** — it auto-generates runnable pytest eval suites from LLM agent traces. Core flow: OTel traces in → 3-stage LLM analysis (Decompose → Intent → Risk) → eval proposals → human review → pytest export.

**Repository:** `~/TraceEval`, MIT-licensed, Python 3.10+. Phase 1 complete (381 tests, 89% bug detection rate).

## Integration Overview

SecondBrain produces OTel-format JSONL trace files from its LLM calls. TraceEval consumes those files to generate evals that catch regressions when models or prompts change.

```
SecondBrain (LLM calls)
  → OpenLLMetry auto-instrumentation
  → BatchSpanProcessor
      ├→ FileSpanExporter → data/traces/YYYY-MM-DD.jsonl → TraceEval
      └→ OTLP exporter → localhost:3000 (self-hosted Langfuse, trace viewer UI)
  → TraceEval analyze + generate + export
  → pytest evals
```

> **Privacy note:** Langfuse is self-hosted via Docker Compose at `etc/langfuse/`.
> All ports bound to `127.0.0.1`. No trace data leaves the machine.
> See `etc/langfuse/docker-compose.yml` for the full stack.

## Phased Approach

| Phase | What | Cost | Status |
|-------|------|------|--------|
| **9.8a** | OpenLLMetry + local JSONL file export | Free | **Done** (TRACE-1) |
| **9.8b** | Langfuse self-hosted (adds trace viewer UI) | Free | **Done** (TRACE-2) |
| **9.8c** | Full platform (LangSmith/Arize/etc.) | Paid | Covered by OTel architecture — swap exporter |

## Documents

- `phase-9.8a-openllmetry-file-export.md` — Design spec for Phase 9.8a
- TraceEval's integration doc: `~/TraceEval/docs/secondbrain-integration/README.md`

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| **OTel spans complement (not replace) UsageStore** | UsageStore handles cost tracking, anomaly detection, admin dashboard. OTel spans feed TraceEval. Different purposes, no conflict. |
| **OpenLLMetry auto-instrumentation over manual spans** | Cheapest option. Zero changes to LLM call sites. Produces OpenInference attributes TraceEval expects natively. |
| **JSONL files are durable artifacts** | Never auto-deleted. Accumulated traces can be bulk-imported into future platforms (Langfuse, LangSmith). A month of real data is more valuable for TraceEval than synthetic test runs. |
| **Tracing is opt-in (disabled by default)** | `SECONDBRAIN_TRACING_ENABLED=true` to activate. No overhead when off. |
