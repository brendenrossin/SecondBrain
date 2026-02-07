# Calendar Integration (Read-Only) — Feasibility Assessment

> **Status:** Not committed. Requires feasibility assessment before entering roadmap.
> **Original proposal:** Phase 8 in brainstorm roadmap
> **Decision date:** 2026-02-07

## Motivation

Read-only calendar access to:
- Link tasks to upcoming calendar events
- Detect scheduling conflicts (task due date vs packed calendar day)
- Suggest time blocks for focused work on high-priority tasks

## Open Questions (Must Answer Before Building)

### Integration approach
- Apple Calendar (EventKit / CalDAV) vs Google Calendar API?
- Local-only (read .ics files or CalDAV on LAN) vs API-based?
- How to handle recurring events?

### Value proposition
- Does the user currently miss task-calendar connections, or is this solving a hypothetical problem?
- Is the calendar view in the Next.js frontend (weekly agenda) already sufficient?

### Architecture
- Calendar events are ephemeral and high-volume — how to avoid index bloat?
- Should calendar data be indexed into the same embedding space, or kept as structured metadata only?

## Risks

- **Low signal-to-noise:** Most calendar events (meetings, standups) don't meaningfully connect to vault notes
- **Auth complexity:** Google Calendar requires OAuth; Apple Calendar requires different integration per platform
- **Maintenance:** Calendar APIs change; recurring event handling is notoriously tricky

## Decision: Build / Defer / Kill

Not yet decided. The value proposition needs validation: would calendar-task linking actually change behavior, or is it nice-to-have?
