# Feature: Task Management UI — Tri-State Status + Update API + Frontend Integration

**Date:** 2026-02-10
**Branch:** main

## Summary

Upgraded the task system from a binary completed/open model to a tri-state status model (open, in_progress, done), added a PATCH API endpoint for updating tasks directly from the UI, and wired up interactive task management across the entire frontend — checkbox toggles, context menus, and a slide-out detail panel.

## Problem / Motivation

Tasks were read-only in the UI. Users had to open Obsidian and manually edit daily notes to change task status or due dates. The binary completed/open model also didn't support the common Obsidian convention of `- [/]` for in-progress tasks, losing information during aggregation.

## Solution

Three work items implemented in dependency order:

1. **Status model upgrade (foundation):** Replaced `completed: bool` with `status: str` throughout the backend — Task dataclass, parser, aggregator, sync engine, and aggregate file writer. The `completed` property is retained as a computed `status == "done"` for backwards compatibility.

2. **Task update API:** Added `PATCH /api/v1/tasks/update` endpoint that locates the latest daily note appearance of a task by composite key (`category|sub_project|normalized_text`), updates the checkbox and/or due date in-place, then re-scans to return the updated state.

3. **Frontend integration:** Added `updateTask()` API client, interactive checkboxes on every task row (both Tasks and Calendar pages), a three-dot menu with status actions, and a slide-out `TaskDetailPanel` with status toggle, date picker, and metadata display.

## Files Modified

**Backend — status model + parser:**
- `src/secondbrain/scripts/task_aggregator.py` — Task.status field, `[/]` parser, `_read_aggregate_statuses()`, `_sync_changes_to_daily()` with full status transitions, `_write_aggregate_file()` In Progress column, `update_task_in_daily()`
- `src/secondbrain/models.py` — `TaskResponse.status`, `TaskUpdateRequest`
- `src/secondbrain/api/tasks.py` — PATCH endpoint, status filter param, cache invalidation
- `src/secondbrain/api/briefing.py` — Exclude in-progress from aging followups

**Tests:**
- `tests/test_task_aggregator.py` — All existing tests updated for status field, new tests for `[/]` parsing, in_progress sync, update_task_in_daily

**Frontend — types + API:**
- `frontend/src/lib/types.ts` — `TaskResponse.status`, `TaskUpdateRequest`
- `frontend/src/lib/api.ts` — `updateTask()`

**Frontend — components:**
- `frontend/src/components/tasks/StatusIcon.tsx` — New shared component (extracted by code-simplifier)
- `frontend/src/components/tasks/TaskItem.tsx` — Checkbox toggle, menu wiring, onUpdate/onSelect props
- `frontend/src/components/tasks/TaskDetailPanel.tsx` — New slide-out panel with status toggle + date picker
- `frontend/src/components/tasks/TaskTree.tsx` — In Progress stat card, detail panel state, onUpdate callbacks
- `frontend/src/components/tasks/TaskCategory.tsx` — Pass onUpdate/onSelect through
- `frontend/src/components/tasks/TaskSubProject.tsx` — Pass onUpdate/onSelect through
- `frontend/src/components/tasks/TaskFilters.tsx` — Added inProgress filter label
- `frontend/src/components/calendar/AgendaTask.tsx` — Checkbox toggle, onUpdate/onSelect props
- `frontend/src/components/calendar/WeeklyAgenda.tsx` — Detail panel state, onUpdate callbacks
- `frontend/src/components/calendar/DaySection.tsx` — Pass onTaskUpdate/onTaskSelect through
- `frontend/src/components/calendar/OverdueSection.tsx` — Pass onTaskUpdate/onTaskSelect through

## Key Decisions & Trade-offs

- **Kept `completed` as computed property:** Rather than removing the boolean field entirely, `AggregatedTask.completed` and `TaskResponse.completed` remain as `status == "done"`. This avoids breaking any existing consumers and the calendar/briefing logic that filters by `completed`.

- **Composite key for task identity:** Tasks are identified by `category|sub_project|normalized_text` rather than by an ID. This matches the existing aggregation logic and avoids needing to generate/store IDs. Trade-off: tasks with identical normalized text in the same category/sub-project would collide, but this is already how aggregation works.

- **Update latest appearance only:** `update_task_in_daily()` modifies only the most recent daily note containing the task, matching the existing convention that the latest appearance's state is authoritative.

- **Re-scan after update:** After writing the file change, the function re-scans all daily notes to return accurate aggregated state. This is slightly expensive but ensures consistency and avoids duplicating aggregation logic.

- **`_STATUS_CHECKBOX` mapping:** Centralized the checkbox string mapping (`open` -> `- [ ]`, `in_progress` -> `- [/]`, `done` -> `- [x]`) as a module-level dict, used by both sync and update functions.

- **5 stat cards instead of 4:** Added "In Progress" as a fifth stat card on the Tasks page. Used `md:grid-cols-5` to accommodate. On mobile it remains 2-column grid so cards wrap naturally.

## Patterns Established

- **`onUpdate` callback pattern:** All task-displaying components accept an optional `onUpdate?: () => void` callback that triggers a data refetch after any mutation. This propagates up through TaskItem -> TaskSubProject -> TaskCategory -> TaskTree.

- **`onSelect` callback pattern:** Similarly, `onSelect?: (task: TaskResponse) => void` propagates up to open the detail panel. The panel state lives in the page-level component (TaskTree or WeeklyAgenda).

- **Shared `StatusIcon` component:** `frontend/src/components/tasks/StatusIcon.tsx` renders the correct icon (Circle/CircleDot/CheckCircle2) for any status string, with configurable size (`sm`/`md`). Use this for all task status display.

- **Optimistic-ish updates:** The UI disables interaction during the PATCH call (opacity + pointer-events-none) rather than doing true optimistic updates. This is simpler and avoids rollback complexity.

## Testing

- 274 backend tests pass (55 in test_task_aggregator.py including 6 new tests for update_task_in_daily)
- Frontend builds clean with TypeScript checks
- Manual verification: API returns `status` field for all 40 vault tasks
- PATCH endpoint returns proper 404 for missing tasks and 500 for unconfigured vault

## Future Considerations

- **Optimistic UI updates:** Currently the UI refetches all tasks after every mutation. For better perceived performance, could apply the change locally first and reconcile after the API responds.
- **Undo support:** No undo for status changes. Could add a toast with an undo button that reverts the PATCH.
- **Batch updates:** Currently one PATCH per task. If users want to bulk-complete tasks, a batch endpoint would be more efficient.
- **"Open in vault" action:** The menu item exists but is a no-op. Would need an Obsidian URI scheme handler (`obsidian://open?vault=...&file=...`).
