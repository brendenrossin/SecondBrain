# Feature: Roadmap Review & Pruning

**Date:** 2026-02-07
**Branch:** main

## Summary

Conducted a comprehensive roadmap review session to critically evaluate brainstormed ideas (from a ChatGPT session) and prune the roadmap down to high-impact, feasible phases. Updated all project documentation to reflect decisions — what was kept, cut, deferred, and why.

## Problem / Motivation

The roadmap had grown from 8 phases to 12+ after a brainstorming session that introduced ambitious ideas: task lifecycle engine with state machine, observer jobs with contradiction detection, ambient intelligence integrations (email, calendar, digest). While creative, many of these ideas violated the project's core principles (vault as source of truth, simplicity over cleverness, suggestion-only) and would have created significant maintenance debt for a single-user system.

## Solution

Acted as PM/architect to review every proposed idea on feasibility, impact, and alignment. Aggressively scoped down or cut proposals, renumbered phases, and created dedicated feature spec files for deferred/exploration items so ideas aren't lost but don't pollute the execution roadmap.

## Files Modified

### Roadmap & Core Docs
- `docs/ROADMAP.md` — Full rewrite with decisions log, renumbered phases, deprecated section
- `CLAUDE.md` — Updated status (Phases 0-4 done), principles, tech stack, phase list
- `docs/PRD.md` — Updated milestones, marked bot gateway obsolete, updated interfaces
- `docs/SOLUTION_ARCHITECTURE.md` — Updated to reflect actual architecture (Next.js, Tailscale, no bot gateway)

### New Feature Specs
- `docs/features/retrieval-transparency.md` — Full spec for next phase (score breakdown, LLM-driven recency)
- `docs/features/proactive-signals-v1.md` — Spec for escalation + recurrence signals only
- `docs/features/DEFERRED-task-lifecycle.md` — Captured rationale for cutting state machine
- `docs/features/EXPLORATION-email-ingestion.md` — Feasibility questions before committing
- `docs/features/EXPLORATION-calendar-integration.md` — Feasibility questions before committing

## Key Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| **Vault stays authoritative** | No application state (task states, signal states) outside the vault. The system is always a read-only view on top of personal notes. This is the single most important architectural constraint. |
| **Cut task lifecycle engine** | A state machine (todo/doing/blocked/waiting/done) creates a source-of-truth conflict with vault-driven tasks. Current heuristics (days_open, due_date) cover the need. |
| **Recency = LLM-driven, not a scoring multiplier** | Instead of a decay formula that risks burying important old notes, pass timestamps to the LLM and let it reason contextually (e.g., prefer the recent grocery list). No calibration needed. |
| **Cut contradiction detection** | Research problem, not a product feature. Low precision would erode trust faster than it adds value. |
| **Cut drift detection** | Requires state tracking the vault architecture doesn't support. Revisit only if task lifecycle engine is ever built. |
| **Phase 4 (remote access) marked done** | Tailscale is live and working from phone. |
| **Phase 5 (bot gateway) marked obsolete** | Next.js frontend already has a working /chat page. |
| **Gradio UI deprecated** | Next.js is the sole frontend going forward. |
| **Broke Phase 8 (ambient intelligence) into separate explorations** | Email, calendar, and digest are three independent integration projects with different feasibility profiles. Bundling them as one phase was misleading. |

## Patterns Established

- **`docs/features/` directory** for individual feature specs, deferred proposals (`DEFERRED-*.md`), and feasibility assessments (`EXPLORATION-*.md`)
- **Decisions log in ROADMAP.md** — captures what was cut and why, so future brainstorms don't re-propose the same ideas without addressing the original objections
- **Naming convention:** `DEFERRED-` prefix = idea has merit but was explicitly postponed with conditions to revisit; `EXPLORATION-` prefix = idea needs feasibility assessment before committing

## Testing

Documentation-only change. Verify by reading updated docs and confirming consistency across ROADMAP.md, CLAUDE.md, PRD.md, and SOLUTION_ARCHITECTURE.md.

## Future Considerations

- The Gradio UI code (`src/secondbrain/ui.py`) still exists and can be removed in a cleanup pass
- The `SECONDBRAIN_GRADIO_PORT` env var and `make ui` command reference Gradio and should be updated when the code is removed
- Phase 5 (retrieval transparency) is the next implementation target — the feature spec is ready
