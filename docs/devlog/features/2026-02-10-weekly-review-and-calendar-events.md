# Feature: Weekly Review Generation + Calendar Events (Phase 7 + 7.5)

**Date:** 2026-02-10
**Branch:** main

## Summary

Implemented two phases: Phase 7 adds template-based weekly review generation from daily notes (no LLM required), and Phase 7.5 adds calendar event support throughout the stack — inbox classification, daily note storage, event parsing, API endpoint, and frontend display.

## Problem / Motivation

Weekly reviews are essential for reflection but tedious to assemble manually. By scanning daily notes for focus items, tasks, notes, and recurring topics, the system auto-generates a `00_Weekly/YYYY-WNN.md` file that captures what happened each week. Calendar events were previously missing from the system — dictated appointments and visits had no way to appear on the calendar view alongside tasks.

## Solution

**Phase 7 — Weekly Review:** Pure data assembly script that scans 7 daily notes per ISO week using existing `parse_daily_note_sections()` and task aggregation functions. Extracts focus items (with day tracking), completed/open tasks (grouped by category), notes, and recurring topics (words appearing across 3+ daily notes). Outputs frontmatter-rich markdown to `00_Weekly/`.

**Phase 7.5 — Calendar Events:** Four-layer implementation:
1. **Inbox classification** — Added `"event"` note type to LLM classification prompt with event-specific fields (`event_title`, `event_date`, `event_time`, `event_end_date`)
2. **Storage** — Events route to daily notes under a `## Events` section, positioned before `## Focus`
3. **Read path** — New `event_parser.py` scans daily notes for `## Events` sections; new `/api/v1/events` endpoint with TTL cache
4. **Frontend** — `AgendaEvent` component (emerald accent, CalendarDays icon), `MultiDayBanner` for spanning events, events rendered above tasks in day sections

## Files Modified

**New files:**
- `src/secondbrain/scripts/weekly_review.py` — Weekly review generator
- `src/secondbrain/scripts/event_parser.py` — Event parser (scan daily notes for `## Events`)
- `src/secondbrain/api/events.py` — Events API endpoint
- `frontend/src/components/calendar/AgendaEvent.tsx` — Single-day event display
- `frontend/src/components/calendar/MultiDayBanner.tsx` — Multi-day event banner
- `tests/test_weekly_review.py` — 17 tests
- `tests/test_event_parser.py` — 14 tests
- `tests/test_events_api.py` — 3 tests

**Modified files:**
- `src/secondbrain/scripts/daily_sync.py` — Added `weekly` command
- `src/secondbrain/scripts/inbox_processor.py` — Event classification, validation, routing, `_route_event()`, `_ensure_events_section()`
- `src/secondbrain/models.py` — `EventResponse` model
- `src/secondbrain/main.py` — Register events router
- `frontend/src/lib/types.ts` — `CalendarEvent` interface
- `frontend/src/lib/api.ts` — `getEvents()` function
- `frontend/src/components/calendar/WeeklyAgenda.tsx` — Fetch events alongside tasks, multi-day banners, pass events to day sections
- `frontend/src/components/calendar/DaySection.tsx` — Accept `events` prop, render above tasks, updated count display
- `Makefile` — `weekly-review` target
- `docs/ROADMAP.md` — Marked Phase 7 and 7.5 done
- `CLAUDE.md` — Updated phase list

## Key Decisions & Trade-offs

- **No LLM for weekly review** — Pure template assembly is faster, cheaper, and deterministic. The data (focus items, tasks, notes) is already structured in daily notes, so LLM adds no value here.
- **ISO week boundaries** — Used `date.fromisocalendar()` for correct Monday-Sunday week boundaries, handles year-boundary edge cases properly.
- **Recurring topics via word frequency** — Simple approach: extract words, exclude stopwords, find those appearing across 3+ daily notes. Good enough without NLP overhead.
- **`## Events` section placement** — Before `## Focus` in daily notes. Events are calendar entries, not actionable items, so they sit separately from tasks/focus.
- **Event format in markdown** — `- HH:MM — title` for timed, `- title` for all-day, `- title (through YYYY-MM-DD)` for multi-day. Regex-parseable, human-readable.
- **Emerald accent for events** — Visually distinguishes events from tasks (which use the blue accent) in the calendar UI.
- **Weekly review is on-demand only** — Not part of `daily_sync all` to avoid generating partial-week reviews during the week. Run via `make weekly-review` or `daily_sync weekly`.

## Patterns Established

- **Event storage in daily notes** — Events live under `## Events` in daily notes, following the same section-based pattern as Focus/Notes/Tasks. Future features should respect this section ordering.
- **`_ensure_events_section()` pattern** — Inserts a new section before `## Focus` if it doesn't exist. Reusable for adding other sections to daily notes.
- **Multi-day event overlap detection** — `get_events_in_range()` uses string comparison of date ranges for overlap. Simple and correct for YYYY-MM-DD format.
- **Frontend event/task co-display** — `DaySection` now accepts both tasks and events, rendering events first. Count label shows "X events, Y tasks".

## Testing

- 34 new tests across 3 test files, all passing
- Full suite: 260 tests pass
- Lint (`ruff check`): clean
- Type check (`mypy`): clean
- Manual verification: backend API responds to `/api/v1/events`, frontend loads calendar page at 200

## Future Considerations

- **Weekly review LLM polish** — Could optionally run an LLM summary pass over the assembled data for more narrative prose. Currently unnecessary.
- **Event editing** — No UI for editing/deleting events yet; users edit daily notes directly.
- **Recurring events** — No support for "every Monday" type events. Would need a separate recurrence format.
- **Event time sorting** — Events within a day section aren't sorted by time in the frontend yet (they arrive sorted from the API, but the component just renders in order).
