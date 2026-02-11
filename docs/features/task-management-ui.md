# Task Management UI -- Status, Due Dates & Detail View

> **Status:** Planned (Phase 8)
> **Estimated effort:** 3-5 days
> **Depends on:** Phase 5 (morning briefing, task aggregator), Phase 7.5 (calendar events)

## Problem

All task updates require opening Obsidian and editing markdown files directly. The SecondBrain UI can display tasks but cannot modify them. The "Mark complete" and "Mark incomplete" buttons in the task overflow menu have no click handlers. Changing a due date means finding the right daily note, locating the task line, and editing the `(due: YYYY-MM-DD)` suffix by hand.

Now that the UI is the daily driver (capture, calendar, briefing all work from the browser), roundtripping to Obsidian for a checkbox toggle is unnecessary friction.

## Solution

Add task write-back to the UI: status changes, due date changes, and a task detail view. The vault remains the source of truth -- the API writes directly to the daily note files, same as if the user edited them in Obsidian.

### Three work items:

---

### Work Item 1: Task Update API

**Goal:** Backend endpoints to change task status and due date.

**Endpoint:**
```
PATCH /api/v1/tasks/update
```

**Request body:**
```json
{
  "text": "Follow up with Snowflake recruiter",
  "category": "Personal",
  "sub_project": "",
  "status": "done",
  "due_date": "2026-02-15"
}
```

**Status values:** `"open"` | `"in_progress"` | `"done"`

**Behavior:**
1. Find the task using the composite key: `category|sub_project|normalized(text)`
2. Locate the task in the **most recent daily note** where it appears (latest appearance is authoritative)
3. Update the checkbox:
   - `"open"` -> `- [ ]`
   - `"in_progress"` -> `- [/]`
   - `"done"` -> `- [x]`
4. Update the due date:
   - If `due_date` is a date string, add/replace `(due: YYYY-MM-DD)` suffix
   - If `due_date` is empty string, remove the `(due: ...)` suffix
   - If `due_date` is `null`/absent, don't change it
5. Invalidate the task cache immediately
6. Return the updated task

**Markdown conventions:**
- `- [ ]` = open (standard markdown checkbox)
- `- [/]` = in progress (Obsidian Tasks plugin convention, renders as a half-filled checkbox)
- `- [x]` = completed (standard markdown checkbox)

**In-progress handling in task aggregator:**
The task aggregator currently treats tasks as `completed: bool`. This needs to expand to a three-value status:
- `_parse_tasks_from_file()` must recognize `- [/]` as `status="in_progress"`
- `AggregatedTask` gets a `status: str` field (`"open"` | `"in_progress"` | `"done"`) replacing `completed: bool`
- Aggregate table shows "In Progress" in the Status column
- The `completed` property on `AggregatedTask` becomes a computed property: `return self.status == "done"`
- This is a **backwards-compatible change** -- existing `- [ ]` and `- [x]` tasks parse correctly, `completed` property still works for callers that use it

**Cache invalidation:**
The task API has a 60-second TTL cache. After a write, clear it immediately so the next GET reflects the change. Simplest approach: increment a cache epoch counter that the GET endpoint checks.

**Files:**
- `src/secondbrain/scripts/task_aggregator.py` -- add `status` field, parse `- [/]`, add `update_task_in_daily()` function
- `src/secondbrain/api/tasks.py` -- add PATCH endpoint, cache invalidation
- `src/secondbrain/models.py` -- add `TaskUpdateRequest` model, update `TaskResponse` with status field

---

### Work Item 2: Frontend Task Detail Panel

**Goal:** Click on a task to see details and take actions.

**Interaction:**
- Click on a task row (in Tasks page or Calendar) -> slide-out panel from the right (or modal)
- Panel shows:
  - Task text (large, prominent)
  - Category > Sub-project label
  - Status selector: three-option toggle (Open / In Progress / Done)
  - Due date: date input field with calendar picker
  - Metadata: days open, first appeared, appearance count
  - Source: which daily note(s) it appears in
- Changes save immediately on interaction (no "Save" button needed)
- Panel closes on outside click or X button

**Quick actions (no panel needed):**
- Checkbox click on task row toggles open <-> done directly (most common action)
- This works on both the Tasks page and Calendar page

**Files:**
- `frontend/src/components/tasks/TaskDetailPanel.tsx` -- new component
- `frontend/src/components/tasks/TaskItem.tsx` -- add click handler, wire overflow menu actions
- `frontend/src/components/calendar/AgendaTask.tsx` -- add checkbox toggle
- `frontend/src/lib/api.ts` -- add `updateTask()` function
- `frontend/src/lib/types.ts` -- update TaskResponse with `status` field, add TaskUpdateRequest

---

### Work Item 3: Task Aggregator Status Model Upgrade

**Goal:** Support three-value status throughout the system.

**Changes to task aggregator:**
- `Task` dataclass: replace `completed: bool` with `status: str` (open/in_progress/done)
- `AggregatedTask`: same change, add `completed` as computed property for backwards compat
- `_parse_tasks_from_file()`: recognize `- [/]` pattern alongside `- [ ]` and `- [x]`
- `_write_aggregate_file()`: show "In Progress" in Status column for in-progress tasks
- `_write_completed_file()`: only include `status == "done"` tasks (unchanged behavior)
- `_read_aggregate_completions()`: parse "In Progress" status from table
- Bi-directional sync: `- [/]` syncs correctly between aggregate and daily notes

**Changes to briefing API:**
- Briefing should distinguish between open and in-progress tasks (in-progress tasks are not "aging follow-ups")

**Changes to frontend types:**
- `TaskResponse.status`: `"open" | "in_progress" | "done"` (replaces `completed: boolean`)
- `TaskResponse.completed`: keep as backwards-compat computed field, or remove and update all consumers
- Tasks page filters: add "In Progress" as a filter option
- Task item visual: different icon/style for in-progress (e.g., half-filled circle or spinner icon)

---

## Implementation Order

```
Work Item 3: Status model upgrade (foundation)
  - Update Task/AggregatedTask dataclasses
  - Update parser to recognize - [/]
  - Update aggregate file writer
  - Update existing tests
Work Item 1: Task Update API (depends on 3)
  - update_task_in_daily() function
  - PATCH endpoint
  - Cache invalidation
  - New tests
Work Item 2: Frontend (depends on 1)
  - TaskDetailPanel component
  - Quick checkbox toggle
  - API client function
  - Wire up existing overflow menu
```

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| **Task creation from UI** | Capture page handles this. Dictate a task, inbox processor classifies and routes it. |
| **Task deletion** | Vault is source of truth. Delete tasks in Obsidian. |
| **Task description/notes field** | User said "don't need to implement now." Can be added later as a body field below the task text in the detail panel. |
| **Drag-and-drop reordering** | Tasks are ordered by due date and age. Manual ordering adds state that doesn't map to vault files. |
| **Subtask management** | The aggregator currently ignores indented subtasks. Supporting them is a separate feature. |
| **Bulk operations** | Select-all, bulk status change, etc. Start with single-task operations. |

## Testing

**Automated:**
- `update_task_in_daily()`: test status change (open->done, done->open, open->in_progress), due date change, due date removal
- `_parse_tasks_from_file()`: test `- [/]` parsing
- API: test PATCH endpoint returns updated task, test cache invalidation
- Aggregate writer: test "In Progress" status in table output
- Backwards compat: all existing tests pass (completed property still works)

**Manual QA:**
- Click checkbox on task row -> task moves to completed
- Click checkbox on completed task -> task moves back to open
- Open task detail -> change status to "In Progress" -> verify daily note updated
- Change due date via date picker -> verify daily note updated
- Verify changes appear on both Tasks page and Calendar page

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Write to daily notes directly, not aggregate** | Daily notes are the source of truth. The aggregate is a derived view. Writing to the aggregate and waiting for sync would add latency and a sync step. |
| **`- [/]` for in-progress** | Obsidian Tasks plugin convention. Renders correctly in Obsidian with a half-filled checkbox. No custom syntax needed. |
| **Immediate save, no Save button** | Task status changes are small, reversible actions. A Save button adds friction for the most common operation (checking off a task). |
| **PATCH not PUT** | Partial updates. You can change status without touching due date, and vice versa. |
| **Composite key, no task IDs** | Tasks are identified by text + category + sub_project. Adding synthetic IDs would require a mapping layer between IDs and vault file locations that could get out of sync. |

---

## Known Minor Issues (future cleanup)

These are non-blocking quality-of-life items identified during PM review. None affect correctness.

| Issue | Detail | Priority |
|-------|--------|----------|
| **Double vault scan on update** | `update_task_in_daily()` calls `scan_daily_notes()` twice (once to find the task, once after writing to return fresh state). Fine at current vault size (~50 notes), worth optimizing at 1000+. | Low |
| **Briefing cache not invalidated on task update** | The tasks API clears its own cache after PATCH, but the briefing endpoint has a separate 60s TTL cache. Checking off a task won't reflect in the briefing for up to 60 seconds. Fix: clear briefing cache from the PATCH handler too. | Low |
| **Silent error handling in frontend** | All three update components (TaskDetailPanel, TaskItem, AgendaTask) swallow API errors silently. The UI stays in its current state, so the user doesn't know a toggle failed. Add a toast/notification on error. | Low |
| **No optimistic UI** | Checkbox toggles wait for the full API round-trip before updating visually. Could feel sluggish on slow connections. Add optimistic state with rollback on error. | Low |
| **Empty source sections after category move** | When all tasks are moved out of a `### Category`, the empty heading lingers in the daily note. Cosmetic only — doesn't affect parsing or aggregation. | Low |
| **Native `<select>` styling** | Category/sub-project dropdowns use browser-default `<select>` which may look off on dark themes. Could replace with a custom dropdown component. | Low |
