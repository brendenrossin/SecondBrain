# Implementation Prompt: Personal Task Subcategories

## Spec

Read the full spec first: `docs/features/personal-task-subcategories.md`

## Context

The single file to modify is `src/secondbrain/scripts/inbox_processor.py`. Tests go in `tests/test_inbox_processor.py`.

## Implementation Steps

### Step 1: Add `PERSONAL_SUB_PROJECTS` constant (WI2 — do first)

Near `TASK_CATEGORIES` (line 26), add a dict mapping subcategory names to short descriptions:

```python
PERSONAL_SUB_PROJECTS: dict[str, str] = {
    "Family": "family logistics, visits, coordination with family members",
    "Rachel": "anything specific to Rachel — relationship, proposal, dates, gifts for Rachel",
    "Gifts": "gifts for anyone (birthdays, holidays, occasions) — EXCEPT gifts for Rachel (use Rachel)",
    "Health": "medical appointments, fitness, wellness",
    "Errands": "one-off errands, pickups, drop-offs",
    "Chores": "recurring household tasks (cleaning, laundry, etc.)",
    "Projects": "personal projects with ongoing scope (e.g., SecondBrain, home automation)",
    "General": "anything that doesn't clearly fit above",
}
```

Using a dict (not a list) so the prompt section can be built dynamically with descriptions.

### Step 2: Update `CLASSIFICATION_PROMPT` (WI1)

Build a prompt section dynamically from the constant and insert it into `CLASSIFICATION_PROMPT`.

Near the existing derived constants (`_CATEGORY_OPTIONS`, `_CATEGORY_LIST`, etc.), add:

```python
_PERSONAL_SUB_PROMPT = "\n".join(
    f'- "{name}": {desc}' for name, desc in PERSONAL_SUB_PROJECTS.items()
)
```

Then insert the following block into `CLASSIFICATION_PROMPT`, after the existing due_date rules section (after line 145, before the final "For daily_note:..." instructions):

```
When category is "Personal", assign sub_project from these subcategories:
{_PERSONAL_SUB_PROMPT}
If unsure between subcategories, prefer "General" over guessing wrong.
```

Use an f-string interpolation of `_PERSONAL_SUB_PROMPT` inside the prompt. The prompt is already an f-string, so this fits naturally.

Do NOT change any other part of the prompt. AT&T and PwC sub_project behavior is unchanged.

### Step 3: Add `_normalize_personal_subcategory()` (WI3)

Add a **new function** — do NOT modify `_validate_classification()`. That function is a pure boolean structural check and should not mutate data.

```python
def _normalize_personal_subcategory(classification: dict[str, Any]) -> None:
    """Remap unrecognized Personal sub_project values to 'General'."""
    # Only applies to tasks with category == "Personal"
    for task in classification.get("tasks", []):
        if task.get("category") == "Personal" and task.get("sub_project"):
            if task["sub_project"] not in PERSONAL_SUB_PROJECTS:
                logger.warning(
                    "Unknown Personal sub_project '%s', remapping to 'General'",
                    task["sub_project"],
                )
                task["sub_project"] = "General"
    # Also check top-level classification sub_project
    if (
        classification.get("category") == "Personal"
        and classification.get("sub_project")
        and classification["sub_project"] not in PERSONAL_SUB_PROJECTS
    ):
        logger.warning(
            "Unknown Personal sub_project '%s', remapping to 'General'",
            classification["sub_project"],
        )
        classification["sub_project"] = "General"
```

Call it in `_classify_with_retry()` after validation passes, before returning:

```python
if _validate_classification(classification):
    _normalize_personal_subcategory(classification)
    return classification
```

This is placed right at line 345-346 in the current code.

## Testing

Add tests to `tests/test_inbox_processor.py`. Follow existing test patterns.

Required tests:

1. **`test_normalize_personal_subcategory_valid`** — Classification with `category: "Personal"`, `sub_project: "Family"` in a task. Verify it's unchanged after normalization.

2. **`test_normalize_personal_subcategory_unknown_remaps_to_general`** — Classification with `category: "Personal"`, `sub_project: "SomeInventedThing"` in a task. Verify it's remapped to `"General"` after normalization.

3. **`test_normalize_personal_subcategory_non_personal_unchanged`** — Classification with `category: "AT&T"`, `sub_project: "AI Receptionist"`. Verify it's left unchanged (no remapping for non-Personal categories).

4. **`test_normalize_personal_subcategory_top_level`** — Classification with top-level `category: "Personal"`, `sub_project: "BadValue"`. Verify the top-level `sub_project` is remapped to `"General"`.

5. **`test_personal_sub_projects_constant_has_general`** — Verify `"General"` is in `PERSONAL_SUB_PROJECTS` (guards against accidental removal of the fallback).

## What NOT to do

- Do NOT modify `_validate_classification()` — it's a boolean structural checker, not a mutator
- Do NOT add subcategories for AT&T or PwC
- Do NOT change the frontend — it already renders sub-projects
- Do NOT retroactively re-categorize existing tasks
- Do NOT make subcategories user-configurable via settings
- Do NOT change `_ensure_task_hierarchy()` or `_ensure_task_category()` — they already handle arbitrary sub_project values

## Commit Workflow

After implementation: `/test-generation` -> `code-simplifier` -> commit.

## Coordination Note

This spec can ship independently of `fix-tasks-lost-on-existing-note-append.md`, but ideally ships together so that tasks routed via the new `_write_tasks_to_daily()` helper also get proper Personal subcategories. If implementing both, do the tasks-lost bug fix first (it doesn't depend on subcategories), then this enhancement (it benefits from the fix being in place).
