# Implementation Prompt: Retroactive Task Recategorization

## Context
We added Personal subcategories (Family, Rachel, Gifts, Health, Errands, Chores, Projects, General) to the inbox processor. Existing Personal tasks in daily notes are all flat under `### Personal` with no `#### Sub-project` headings. We need to move them into the correct subcategories.

One task also needs to move from Personal to PwC (different top-level category).

## Approach
Write a one-time script `src/secondbrain/scripts/recategorize_tasks.py` that:
1. Uses `update_task_in_daily()` from `task_aggregator.py` to reassign each task
2. After all reassignments, calls `sync_tasks()` to regenerate All Tasks.md and Completed Tasks.md
3. Has `--dry-run` mode that prints what would change without writing

The `update_task_in_daily()` function already supports `new_category` and `new_sub_project` parameters. It modifies ALL daily notes where a task appears, moving the task line to the correct `### Category` / `#### Sub-project` heading.

## Task Mappings

These are the confirmed mappings (all tasks are currently under flat `### Personal` in daily notes):

```python
RECATEGORIZATIONS = [
    # (task_text_substring, new_category, new_sub_project)
    # Gifts
    ("Confer with Rachel on which wines Chad should get", "Personal", "Gifts"),
    ("Follow up with Chad on wine selection", "Personal", "Gifts"),
    ("Get Evan (sister) a birthday/christmas gift", "Personal", "Gifts"),
    # Chores
    ("Take out the trash", "Personal", "Chores"),
    ("Throw out the rat trap", "Personal", "Chores"),
    ("Finish laundry", "Personal", "Chores"),
    # Errands
    ("Get propane tanks", "Personal", "Errands"),
    ("Call Gone Bananas Bread", "Personal", "Errands"),
    # Health
    ("Look into getting a dermatologist appointment", "Personal", "Health"),
    # Projects
    ("Complete Azure AI engineering AZ-102 Udemy course", "Personal", "Projects"),
    ("Finish Langchain course on Coursera", "Personal", "Projects"),
    ("Start next Coursera course after Azure certification", "Personal", "Projects"),
    # General (no sub_project change needed for these — they stay flat Personal,
    # but we assign "General" so they group properly)
    ("Obtain W2 from Genmark", "Personal", "General"),
    ("Finish taxes, including all investment accounts", "Personal", "General"),
    ("Follow up on David's emails", "Personal", "General"),
    # PwC (category change — moves from Personal to PwC)
    ("Go over Azure AI-102 learning path and take practice tests", "PwC", "Admin"),
]
```

## Implementation Steps

1. **Read `src/secondbrain/scripts/task_aggregator.py`** to understand `update_task_in_daily()`, `scan_daily_notes()`, and `sync_tasks()`. The key function signature is:
   ```python
   def update_task_in_daily(vault_path, task_text, new_status=None, new_due_date=None, new_category=None, new_sub_project=None)
   ```
   It matches tasks by normalized text (lowercased, stripped punctuation). It returns the number of daily notes updated.

2. **Write `src/secondbrain/scripts/recategorize_tasks.py`**:
   - Import `scan_daily_notes`, `aggregate_tasks`, `update_task_in_daily`, `sync_tasks` from task_aggregator
   - Import `get_settings` from config
   - For each mapping in `RECATEGORIZATIONS`:
     - Find the matching task in the aggregated task list (substring match on task text)
     - Call `update_task_in_daily(vault_path, matched_task_text, new_category=cat, new_sub_project=sub)`
     - Log what was moved
   - After all moves, call `sync_tasks(vault_path)` to regenerate aggregate files
   - Support `--dry-run` flag

3. **Run the script** (not dry-run) to apply changes

4. **Verify** by reading the updated All Tasks.md to confirm tasks are in correct subcategories

## Important Notes
- The Rachel sub-project tasks (5 proposal tasks) were already injected correctly — don't touch those
- `update_task_in_daily()` modifies daily notes in-place — it uses `_move_task_to_category()` which physically moves task lines between heading sections
- After running, the hourly sync will pick up the changes, but we also call `sync_tasks()` at the end of the script for immediate effect
- This script is a one-time utility (like inject_tasks.py) — keep it in `src/secondbrain/scripts/` for potential future use

## Out of Scope
- Do NOT modify the inbox processor or classification prompt
- Do NOT modify frontend components
- Do NOT create tests for this one-time script (it's a data migration utility)

## Commit Workflow
After running successfully: `code-simplifier` → commit with message like "Retroactively categorize existing Personal tasks into subcategories"
