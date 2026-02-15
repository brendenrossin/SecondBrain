# Implementation Prompt: Fix Tasks Lost on Existing Note Append

## Spec

Read the full spec first: `docs/features/fix-tasks-lost-on-existing-note-append.md`

## Context

The single file to modify is `src/secondbrain/scripts/inbox_processor.py`. Tests go in `tests/test_inbox_processor.py`.

## Implementation Steps

### Step 1: Add `_write_tasks_to_daily()` helper (WI1)

Add a new function near `_route_daily_note()` (around line 592). Signature:

```python
def _write_tasks_to_daily(classification: dict[str, Any], vault_path: Path) -> str | None:
```

Logic:
1. Read `classification.get("tasks", [])`. If empty, return `None` (no-op).
2. Get date: `classification.get("date", datetime.now().strftime("%Y-%m-%d"))`.
3. Resolve daily file: `vault_path / VAULT_FOLDERS["daily"] / f"{date_str}.md"`.
4. Build a **tasks-only classification dict** to pass downstream:
   ```python
   tasks_only = {"tasks": classification["tasks"], "focus_items": [], "notes_items": [], "tags": []}
   ```
   This prevents `_append_to_daily()` from duplicating focus/notes items.
5. If the daily file exists, call `_append_to_daily(daily_file, tasks_only)`.
6. If it doesn't exist, call `_create_daily_note(daily_file, tasks_only, date_str)` (creates a minimal daily note with just tasks).
7. Return a descriptive string like `"Wrote {n} task(s) to 00_Daily/{date_str}.md"`.

Dedup is already handled: `_append_to_daily()` checks `task_text in content` before writing each task (line 626).

### Step 2: Wire up calls in `_process_single_file()` (WI2)

In `_process_single_file()` (starts at line 358), add `_write_tasks_to_daily()` calls after the two paths that currently lose tasks:

**After the existing-note path (line 390):**
```python
if existing_note and isinstance(existing_note, str):
    for folder in [VAULT_FOLDERS["notes"], VAULT_FOLDERS["concepts"]]:
        if (vault_path / folder / f"{existing_note}.md").exists():
            action = _append_to_existing_note(classification, vault_path, folder)
            _write_tasks_to_daily(classification, vault_path)  # <-- ADD
            break
    else:
        existing_note = None
```

**After the folder routing paths (lines 404-414):**
The cleanest approach: after the `if not existing_note` block resolves `action`, add a single call that covers note/project/concept:

```python
if not existing_note or not isinstance(existing_note, str):
    if note_type == "living_document":
        action = _route_living_document(classification, vault_path)
    elif note_type == "event":
        action = _route_event(classification, vault_path)
    elif note_type == "daily_note":
        action = _route_daily_note(classification, vault_path)
    elif note_type == "project":
        action = _route_to_folder(classification, vault_path, VAULT_FOLDERS["projects"], "project")
        _write_tasks_to_daily(classification, vault_path)  # <-- ADD
    elif note_type == "concept":
        action = _route_to_folder(classification, vault_path, VAULT_FOLDERS["concepts"], "concept")
        _write_tasks_to_daily(classification, vault_path)  # <-- ADD
    else:
        action = _route_to_folder(classification, vault_path, VAULT_FOLDERS["notes"], "note")
        _write_tasks_to_daily(classification, vault_path)  # <-- ADD
```

Do NOT add after `_route_daily_note()` (already writes tasks), `_route_event()` (events aren't tasks), or `_route_living_document()` (living docs don't contain tasks).

### Step 3: Add DEBUG logging in `_classify_with_retry()` (WI3)

In `_classify_with_retry()` (line 329), after the validation check passes (line 345-346), add:

```python
if _validate_classification(classification):
    logger.debug("Classification result: %s", json.dumps(classification, indent=2))
    return classification
```

`json` is already imported (line 6).

## Testing

Add tests to `tests/test_inbox_processor.py`. The file already has tests for `_append_to_daily`, `_create_daily_note`, `_ensure_task_hierarchy`, etc. — follow the same patterns (tmp_path fixtures, direct function calls).

Required tests:

1. **`test_write_tasks_to_daily_creates_new_daily_note`** — No daily note exists. Call `_write_tasks_to_daily()` with a classification containing tasks. Verify the daily note was created with correct task checkboxes under `## Tasks > ### Category > #### Sub-project`.

2. **`test_write_tasks_to_daily_appends_to_existing_daily_note`** — Daily note exists with `## Tasks` section. Call `_write_tasks_to_daily()`. Verify tasks were appended under the correct headings without duplicating existing content.

3. **`test_write_tasks_to_daily_noop_when_no_tasks`** — Classification has `tasks: []`. Verify the function returns `None` and no file is created/modified.

4. **`test_write_tasks_to_daily_skips_duplicate_tasks`** — Daily note already contains a task with the same text. Verify the task is skipped (not duplicated).

5. **`test_process_existing_note_also_writes_tasks`** — Integration test. Create an existing note in `10_Notes/`. Build a classification with `existing_note` set AND a `tasks` array. Mock the LLM to return this classification. Call `_process_single_file()`. Verify: (a) content was appended to the existing note, (b) tasks were written to the daily note.

## What NOT to do

- Do not change `_append_to_existing_note()` — it correctly handles prose content
- Do not change `_route_to_folder()` — it correctly creates note files
- Do not change the classification prompt — the LLM behavior is correct
- Do not add task dedup beyond what `_append_to_daily()` already does
- Do not refactor existing routing functions

## Commit Workflow

After implementation: `/test-generation` -> `code-simplifier` -> commit.
