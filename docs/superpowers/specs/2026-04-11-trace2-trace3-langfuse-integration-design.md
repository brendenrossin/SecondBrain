# TRACE-2 + TRACE-3: Langfuse Integration Design

**Date:** 2026-04-11
**Tickets:** TRACE-2 (Langfuse free tier integration), TRACE-3 (full platform)
**Estimate:** 1d (combined — TRACE-3 collapses into TRACE-2)

## Problem

SecondBrain has OTel auto-instrumentation (TRACE-1) writing LLM trace spans to JSONL files. These files are machine-readable for downstream eval tooling but offer no human-friendly trace viewer. Developers need a way to visually inspect trace timelines, token counts, and call hierarchies without parsing JSONL.

## Solution

Add Langfuse's OpenTelemetry exporter as a second span destination alongside the existing `FileSpanExporter`. Dual-write: JSONL continues for eval tooling consumption, Langfuse provides the trace viewer UI via their free-tier web dashboard.

TRACE-3 ("full platform — LangSmith/Arize, only if warranted") is closed by this design: any OTel-compatible backend can be added by swapping/adding an exporter. The architecture is already platform-agnostic.

## Architecture

```
OpenLLMetry auto-instruments Anthropic/OpenAI SDK calls
    │
    ▼
BatchSpanProcessor
    │
    ├──► FileSpanExporter → data/traces/YYYY-MM-DD.jsonl  (eval tooling)
    │
    └──► LangfuseExporter → Langfuse cloud (trace viewer UI)
```

Zero changes to LLM call sites. Zero changes to UsageStore. Zero frontend changes.

## Configuration

Three new env vars (add to `.env`):

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...      # From Langfuse dashboard
LANGFUSE_SECRET_KEY=sk-lf-...      # From Langfuse dashboard
LANGFUSE_HOST=https://cloud.langfuse.com  # Free tier default
```

Two new settings in `config.py`:

```python
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
langfuse_host: str = "https://cloud.langfuse.com"
```

### Behavior Matrix

| `tracing_enabled` | Langfuse keys set | Result |
|---|---|---|
| `false` | any | No-op (zero overhead) |
| `true` | no | JSONL only (current behavior) |
| `true` | yes | Dual-write: JSONL + Langfuse |

## Changes

### `src/secondbrain/tracing.py`
- Import `LangfuseExporter` from the `langfuse` package
- In `init_tracing()`, after creating `FileSpanExporter`, check if Langfuse keys are configured
- If yes, create `LangfuseExporter` and add a second `BatchSpanProcessor` to the `TracerProvider`
- Log which exporters are active at startup

### `src/secondbrain/config.py`
- Add `langfuse_public_key`, `langfuse_secret_key`, `langfuse_host` fields

### `pyproject.toml`
- Add `langfuse` to dependencies

### Tests
- Test dual-export initialization (both exporters created when keys present)
- Test JSONL-only fallback (no Langfuse keys → only FileSpanExporter)
- Test no-op when tracing disabled (unchanged)
- Test graceful handling if Langfuse exporter fails to initialize

## Dependencies

- `langfuse` Python package (includes OTel exporter)

## What's NOT in scope

- No UI changes (Langfuse dashboard IS the UI)
- No new API endpoints
- No changes to UsageStore or admin dashboard
- No Langfuse SDK decorators (`@observe`) — we use the OTel exporter path
- No removal of OpenLLMetry — it remains the instrumentation layer

## Langfuse Setup Guide

### Creating a Langfuse Account (Free Tier)

1. Go to [cloud.langfuse.com](https://cloud.langfuse.com) and sign up (GitHub or email)
2. Create a new **Project** (e.g., "SecondBrain")
3. Go to **Settings → API Keys** in the left sidebar
4. Click **Create new API keys**
5. Copy the **Public Key** (`pk-lf-...`) and **Secret Key** (`sk-lf-...`)
6. Add them to your SecondBrain `.env` file:
   ```bash
   SECONDBRAIN_TRACING_ENABLED=true
   LANGFUSE_PUBLIC_KEY=pk-lf-your-public-key
   LANGFUSE_SECRET_KEY=sk-lf-your-secret-key
   LANGFUSE_HOST=https://cloud.langfuse.com
   ```
7. Restart the API server — traces will start appearing in the Langfuse dashboard within seconds

### Free Tier Limits

- 50k observations/month (an "observation" is roughly one LLM call span)
- At SecondBrain's current volume (~50 spans/day), this gives ~1000 days of headroom
- No credit card required

### Verifying It Works

After restarting with keys configured:
1. Ask a question in the SecondBrain chat
2. Open [cloud.langfuse.com](https://cloud.langfuse.com) → your project → **Traces**
3. You should see a trace with spans for: retrieval, reranking, answer generation
4. Click into a trace to see the full call hierarchy, token counts, and latencies
