# Feature: Morning Briefing Dashboard

**Date:** 2026-02-09
**Branch:** main

## Summary

Added a Morning Briefing Dashboard as the app's home page (`/`). When you open the app, you instantly see what your day looks like: overdue tasks, tasks due today, aging follow-ups, and yesterday's focus/notes context. Pure data assembly with no LLM needed.

## Problem / Motivation

Previously, `/` redirected to `/tasks`, which showed all tasks in a tree view. There was no at-a-glance summary of what needs attention today. The ROADMAP explicitly called for "when you open the app, instantly know what your day looks like" as Phase 5's first deliverable.

## Solution

Full-stack implementation across backend (Python/FastAPI) and frontend (Next.js):

1. **Daily note parser** — Added `parse_daily_note_sections()` and `find_recent_daily_context()` to `task_aggregator.py` to extract `## Focus` and `## Notes` bullets from recent daily notes, with a 3-day lookback (handles weekends).

2. **Briefing API** — New `GET /api/v1/briefing` endpoint that assembles overdue tasks, due-today tasks, aging follow-ups (no due date, >3 days open), yesterday's context, and total open count. Uses 60s TTL cache matching the existing tasks.py pattern.

3. **MorningBriefing component** — Full dashboard UI with stat cards, task sections (conditionally rendered), yesterday's context, skeleton loading, error state with retry, and an all-clear state when nothing is urgent.

4. **Navigation** — Added "Home" (LayoutDashboard icon) as first item in sidebar and mobile nav. Fixed root-path active check (`pathname === "/"` exact match to avoid matching all paths).

## Files Modified

**Backend:**
- `src/secondbrain/scripts/task_aggregator.py` — +DailyNoteContext dataclass, +parse_daily_note_sections, +find_recent_daily_context
- `src/secondbrain/models.py` — +BriefingTask, +DailyContext, +BriefingResponse
- `src/secondbrain/api/briefing.py` — New: GET /api/v1/briefing endpoint
- `src/secondbrain/main.py` — Register briefing_router

**Tests:**
- `tests/test_briefing.py` — New: 13 tests for section parsing and lookback logic

**Frontend:**
- `frontend/src/lib/types.ts` — +BriefingTask, +DailyContext, +BriefingResponse interfaces
- `frontend/src/lib/api.ts` — +getBriefing() function
- `frontend/src/components/briefing/MorningBriefing.tsx` — New: full briefing UI component
- `frontend/src/app/(dashboard)/page.tsx` — Replace redirect with MorningBriefing page
- `frontend/src/components/layout/Sidebar.tsx` — +Home nav item, +NAV_COLORS for "/", fixed root active check
- `frontend/src/components/layout/MobileNav.tsx` — +Home tab, fixed root active check

## Key Decisions & Trade-offs

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Parser location | `task_aggregator.py` | Already reads `00_Daily/` files and understands the format. Natural extension (~50 lines). |
| Weekend/gap handling | 3-day lookback from yesterday | Monday briefing shows Friday's context. Skips today (today's note wouldn't have yesterday's context). |
| Aging threshold | >3 days open, no due date | Filters out brand-new tasks that don't need attention yet. Matches existing "days_open" concept. |
| Home page approach | Replace redirect with real page | Root URL is what loads first. Tasks page stays as the drill-down view. |
| Root active check | Exact match `pathname === "/"` | `startsWith("/")` would match all paths, incorrectly highlighting Home for every page. |

## Patterns Established

- **Daily note section parsing**: Reusable pattern for extracting content from specific `## ` sections in daily notes. Can be extended for other sections.
- **Briefing API caching**: Same 60s TTL cache pattern as tasks.py. Both can share cache invalidation in the future.
- **Conditional card rendering**: Each briefing section only renders when it has data. All-clear state shows when nothing is urgent.

## Testing

- 13 new unit tests (187 total, all passing) covering section parsing, empty handling, file-not-found, lookback logic, weekend gaps, and preference for most recent
- `make check` passes (lint + format + typecheck + tests)
- `curl http://localhost:8000/api/v1/briefing` returns correct JSON with real vault data
- Frontend serves 200 on both `/` and `/tasks`

## Future Considerations

- **Cache invalidation**: Briefing and tasks endpoints have independent caches. Could share invalidation when tasks are updated.
- **Streaking/habits**: Could add "consecutive days with daily notes" or similar engagement metrics.
- **Quick actions**: Briefing tasks could have quick-complete buttons (requires write-back, Phase 8).
- **Customizable aging threshold**: Currently hardcoded at 3 days. Could be user-configurable.
