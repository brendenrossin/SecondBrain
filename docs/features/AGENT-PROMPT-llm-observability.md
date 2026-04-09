# Agent Prompt: Implement LLM Observability & Tracing

Copy everything below this line and paste it as your first message to a new Claude Code session.

---

## Your Task

Implement the LLM Observability & Tracing feature for SecondBrain. This adds per-call latency tracking, trace correlation, error/fallback visibility, anomaly detection, and an enhanced admin dashboard — so we never have another invisible $300/month LLM cost bug.

## Before Writing Any Code

**Create a feature branch from main:**

```bash
git checkout main && git pull
git checkout -b feature/llm-observability-tracing
```

All commits go on this branch. Do NOT commit directly to main. When the feature is complete, we'll merge via PR.

## How to Start

Read these two documents **in order** before writing any code:

1. **Feature spec** — `docs/features/llm-observability-tracing.md`
   - Problem statement, architecture decision (extend SQLite + Next.js, NOT LangSmith), corrected call site inventory, all 7 work items, risk assessment, design decisions.

2. **Implementation prompt** — `docs/features/PROMPT-llm-observability-tracing.md`
   - Step-by-step implementation instructions with exact file paths, code patterns, and what to change in each file. This is your primary guide. Follow it in order (Steps 1–6).

**Do NOT implement WI 7 (Evals)** — it's explicitly deferred.

## Implementation Sequence

Follow these steps in order. Each builds on the prior:

1. **Step 1: Schema migration + pricing guardrails** — `stores/usage.py`
2. **Step 2: Instrument all 4 LLM call sites** — reranker, answerer, llm_client, extractor, inbox_processor, ask.py, daily_sync.py
3. **Step 3: Anomaly detection** — `stores/usage.py`
4. **Step 4: Backend API endpoints** — `api/admin.py`, `models.py`
5. **Step 5: Enhanced admin dashboard** — frontend types, API client, AdminDashboard component
6. **Step 6: Background process health metrics** — `daily_sync.py`, `inbox_processor.py`

## Critical Implementation Rules

- **trace_id is passed as an explicit parameter**, not via context vars. Reranker and Answerer are singletons (created via `@lru_cache`), so trace_id must be per-call.
- **Log EVERY provider attempt, including failures.** When Anthropic fails and Ollama succeeds in the LLMClient fallback chain, log BOTH: the Anthropic call with `status="error"` AND the Ollama call with `status="ok"`. This is 2 rows, not 1. The old pattern of only logging the successful call is what made the $300/month bug invisible.
- **Reranker fallback to similarity scores must log `status="fallback"`**. Currently this silent fallback is completely invisible.
- **`calculate_cost()` must log a warning for unknown models**, not silently return $0.00.
- **Schema migration uses `ALTER TABLE ADD COLUMN`** with try/except for idempotency. No data loss.
- **Frontend uses CSS-based rendering** — no new charting libraries. Match the existing pattern in AdminDashboard.tsx (glass-card, StatCard, inline flexbox charts).

## Commit Workflow

After completing each logical step (or when all steps are done):

1. Run `/test-generation` on modified files with business logic
2. Run `code-simplifier` to ensure code quality
3. Commit with a descriptive message

## After Implementation

Restart both services and verify:

```bash
# Backend
launchctl unload ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 2 && kill -9 $(lsof -ti:8000) 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 3 && curl -s http://localhost:8000/health

# Frontend
cd /Users/brentrossin/SecondBrain/frontend && npm run build
launchctl unload ~/Library/LaunchAgents/com.secondbrain.ui.plist
sleep 2 && kill -9 $(lsof -ti:7860) 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.secondbrain.ui.plist
sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:7860/
```

**Verification test:** Send a chat query via the frontend, then check the admin dashboard Traces tab. You should see 2 correlated calls (rerank + answer) sharing a trace_id, each with latency and status.

## When Done

Push the feature branch and create a PR:

```bash
git push -u origin feature/llm-observability-tracing
```

Then create a PR targeting `main` with a summary of what was implemented. Do NOT merge — the user will review and merge.
