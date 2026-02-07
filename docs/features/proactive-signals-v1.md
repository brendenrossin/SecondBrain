# Proactive Signals v1

> **Status:** Planned (Phase 6)
> **Estimated effort:** 1-2 weeks
> **Depends on:** Phases 1-3 (done), daily sync pipeline (done)

## Problem

The system currently only responds when asked. It has no mechanism to proactively surface important information — approaching deadlines, recurring themes, or items that need attention.

## Signal Types (v1 — start small)

### Escalation Signals
- **Trigger:** Tasks with approaching or overdue deadlines
- **Data source:** Task aggregator (already extracts due_date, days_open)
- **Confidence:** High (deterministic — date math, not inference)
- **Example:** "3 tasks due this week: [task1], [task2], [task3]"

### Recurrence Signals
- **Trigger:** Same entity or topic appearing across multiple recent notes
- **Data source:** Metadata extraction (entities, key phrases)
- **Confidence:** Medium-High (frequency count over time window)
- **Example:** "You've mentioned 'vendor evaluation' in 4 notes this week — consider creating a dedicated note"

## Signal Schema

```python
@dataclass
class Signal:
    signal_type: str          # "escalation" | "recurrence"
    summary: str              # Human-readable description
    confidence: float         # 0.0 - 1.0 (only surface if > 0.8)
    evidence: list[str]       # Citation IDs / note paths
    suggested_next_step: str  # "Review overdue tasks" / "Create note for X"
    created_at: str           # ISO timestamp
```

## Architecture

- **No new infrastructure.** The signal pipeline runs as a post-processing step in the existing daily sync (`make daily-sync`).
- Inputs: aggregated tasks, extracted entities/dates from metadata store
- Outputs: signals written to a simple JSON file (`data/signals.json`) or returned via API
- API endpoint: `GET /api/v1/signals` (returns today's signals)

## UI Integration

- Dashboard card or dedicated section on the Tasks page
- Show 1-3 highest-confidence signals per day (hard cap)
- Each signal has: summary, evidence links, one-click action (create task in vault / dismiss)
- Dismissed signals don't reappear

## Safety Rules

- Signals are **suggestions only** — no side effects, no writes, no notifications
- High confidence threshold: only surface signals with confidence > 0.8
- Low volume: max 3 signals per day, even if more qualify
- Every signal links to source evidence (citations)

## What's Explicitly Excluded (and Why)

| Idea | Why Excluded |
|------|-------------|
| **Drift detection** (tasks repeatedly postponed) | Requires tracking task state changes over time. Current vault-driven architecture doesn't store state transitions. Revisit if task lifecycle engine is ever built. |
| **Contradiction detection** (conflicting notes) | Research problem. Determining what constitutes a "decision" and finding conflicts requires deep semantic understanding + temporal ordering. LLM-heavy, error-prone, low precision. Would erode trust. |
| **Long-running observer agent** | Unnecessary complexity. A simple post-sync batch job achieves the same result. |
| **Push notifications** | Violates suggestion-only principle. The user checks signals when they want to. |

## Open Questions

- Should signals persist across days (rolling 7-day window) or be regenerated fresh each sync?
- How to handle signal fatigue if the same escalation fires daily? Suppress after N days, or always show?
