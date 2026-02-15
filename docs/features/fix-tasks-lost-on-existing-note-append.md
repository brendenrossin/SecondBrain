# Fix: Tasks Lost When Capture Appends to Existing Note

> **Status:** Planned (Bug Fix)
> **Estimated effort:** < 1 day
> **Depends on:** None

## Problem

When a captured note is classified as matching an existing note (e.g., "Rachel's Engagement Ring"), the inbox processor routes it through `_append_to_existing_note()`. This function **only** appends the `classification["content"]` field as prose text under a date heading. It completely ignores the `classification["tasks"]` array.

This means any actionable tasks the LLM extracts — with categories, sub-projects, and due dates — are silently discarded. They never appear in any daily note's `## Tasks` section, so they're invisible to the task aggregator, the All Tasks file, the briefing, and the frontend task views.

**Real-world example (2026-02-15):** A capture about proposal planning contained 5 tasks with specific deadlines ("by end of March", "by end of February", etc.). The LLM correctly matched it to the existing "Rachel's Engagement Ring" note. The content was appended as bullet points, but none of the 5 tasks were written as checkboxes in the daily note. They don't appear in All Tasks.

The same gap exists in `_route_to_folder()` (used for `note`, `project`, `concept` types when `existing_note` is not set) — it also ignores the `tasks` array. However, that path is less likely to have tasks since the LLM is instructed to use `daily_note` type for task-heavy content. The `existing_note` path is the primary issue because the classification prompt forces `note_type` to `"note"` when `existing_note` is set, bypassing the daily_note routing entirely.

## Solution

When any routing path receives a classification that contains a non-empty `tasks` array, those tasks should **also** be written to the appropriate daily note's `## Tasks` section — regardless of which route the content itself takes.

This is a "do both" fix: content goes where the LLM says (existing note, new note, concept, etc.), and tasks **always** go to the daily note.

### Work Item 1: Extract task-writing into a reusable function

**Goal:** Make it possible to write tasks to a daily note from any routing path, not just `_route_daily_note`.

**Behavior:**
- Create a `_write_tasks_to_daily(classification: dict, vault_path: Path) -> None` helper that:
  1. Reads `classification["tasks"]` — if empty or missing, returns immediately (no-op)
  2. Determines the date from `classification["date"]` (fallback: today)
  3. Finds or creates the daily note at `00_Daily/{date}.md`
  4. If the daily note exists, calls `_append_to_daily()` with a classification dict containing only the tasks (no focus/notes items, to avoid duplicating non-task content)
  5. If the daily note doesn't exist, calls `_create_daily_note()` with a minimal classification (just the tasks)
- Includes duplicate detection: if a task's text already appears in the daily note (same check `_append_to_daily` already does with `task_text in content`), skip it

**Files:** `src/secondbrain/scripts/inbox_processor.py`

### Work Item 2: Call task-writing from existing-note and folder routing paths

**Goal:** Ensure tasks are written to the daily note whenever a non-daily routing path processes a classification with tasks.

**Behavior:**
- In `_process_single_file()`, after `_append_to_existing_note()` returns, call `_write_tasks_to_daily(classification, vault_path)`
- In `_process_single_file()`, after `_route_to_folder()` returns (for note/project/concept types), call `_write_tasks_to_daily(classification, vault_path)`
- Do NOT call it after `_route_daily_note()` (already writes tasks), `_route_event()` (events aren't tasks), or `_route_living_document()` (living docs don't contain tasks)

**Files:** `src/secondbrain/scripts/inbox_processor.py`

### Work Item 3: Add DEBUG logging for classification JSON

**Goal:** Make it possible to diagnose future routing issues by logging what the LLM returned.

**Behavior:**
- In `_classify_with_retry()`, after successful classification, log the full classification dict at DEBUG level
- Log format: `logger.debug("Classification result: %s", json.dumps(classification, indent=2))`
- This is DEBUG-only — won't appear in normal logs unless `--verbose` is passed

**Files:** `src/secondbrain/scripts/inbox_processor.py`

## Implementation Order

1. WI1 (extract helper) — no dependencies
2. WI2 (wire up calls) — depends on WI1
3. WI3 (logging) — independent, can be done in parallel with WI1-2

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| Changing the classification prompt | The LLM's classification behavior is correct — the code just doesn't act on it |
| Changing how `_append_to_existing_note` writes content | The prose append behavior is fine; tasks should go to daily note, not the existing note |
| Re-processing old captures | Handled by a separate retroactive fix script |
| Task deduplication across captures | `_append_to_daily` already skips tasks whose text appears in the daily note |

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Duplicate tasks if LLM puts same text in both `content` and `tasks` | Low — cosmetic, user can delete | `_append_to_daily` already does text-in-content dedup |
| Tasks written to wrong date if `classification["date"]` is off | Low — LLM usually picks today for captures | Fallback to `datetime.now()` if date is missing |
| No risk of data loss | N/A — only adds new checkbox lines, never modifies existing content | N/A |

## Testing

**Automated:**
- Unit test: `_write_tasks_to_daily` creates tasks in a new daily note
- Unit test: `_write_tasks_to_daily` appends tasks to an existing daily note
- Unit test: `_write_tasks_to_daily` is a no-op when `tasks` array is empty
- Unit test: `_write_tasks_to_daily` skips duplicate task text
- Integration test: `_process_single_file` with `existing_note` set writes both content to existing note AND tasks to daily note

**Manual QA:**
- Capture a note that references an existing vault note and contains tasks
- Verify content appended to existing note AND tasks appear in today's daily note
- Run task sync and verify tasks appear in All Tasks.md

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Write tasks to daily note, not to the existing note | The task aggregator only scans daily notes — tasks must live there to be tracked. The existing note gets the prose context. |
| Call `_write_tasks_to_daily` from `_process_single_file` rather than inside each routing function | Keeps routing functions focused on their primary job; centralizes the "also write tasks" logic in one place |
| Use a tasks-only classification dict when calling `_append_to_daily` | Prevents duplicating focus_items or notes_items that may have already been routed elsewhere |
| DEBUG-level classification logging | Verbose enough for diagnosis, quiet enough for production |

## Known Minor Issues

| # | Issue | Notes |
|---|-------|-------|
| 1 | When building the tasks-only dict for `_append_to_daily()`, explicitly set `focus_items: []` and `notes_items: []` rather than omitting the keys | `_append_to_daily()` uses `.get("focus_items", [])` so omitting keys works, but explicit empty lists are safer and more readable |
| 2 | Task dedup in `_append_to_daily()` uses substring match (`task_text in content`), not exact task-line match | A task "Call Rachel" would be skipped if the file contains "Call Rachel's mom". Consistent with existing behavior — not introduced by this fix. |
| 3 | `_route_to_folder()` confirmed to also ignore `tasks` array — the WI2 call after folder routing covers this secondary path | Less likely to have tasks since the LLM uses `daily_note` type for task-heavy content, but the coverage is correct |
