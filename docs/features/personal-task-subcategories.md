# Personal Task Subcategories

> **Status:** Planned (Enhancement)
> **Estimated effort:** < 1 day
> **Depends on:** None (can ship independently of the tasks-lost bug fix, but ideally ships together)

## Problem

The Personal task category is a flat bucket with no subcategories. AT&T has sub-projects (AI Receptionist, Welcome Agent), but Personal tasks — which span family logistics, health, errands, gifts, personal projects, and more — all land in one undifferentiated list.

As the vault grows, this makes it harder to scan, prioritize, and track personal tasks. The user already has diverse personal task types (proposal planning, gift deadlines, grocery runs, SecondBrain development) that would benefit from structure.

## Solution

Add predefined subcategories for the Personal category and update the LLM classification prompt to assign `sub_project` values for personal tasks. The sub-project infrastructure already exists in the codebase (headings in daily notes, grouping in the aggregator, API support) — it just needs to be activated for Personal.

### Personal Subcategories

| Subcategory | What belongs here | Examples |
|-------------|-------------------|----------|
| **Family** | Family logistics, visits, coordination | "Ask Meagan if she and Chad can come", "Plan trip to see parents" |
| **Rachel** | Anything specific to Rachel (relationship, proposal, dates) | "Work with Lisa on ring sourcing", "Hire photographer for proposal", "Plan date night" |
| **Gifts** | Gifts for anyone — birthdays, holidays, occasions | "Get Evan a birthday/Christmas gift", "Order anniversary present" |
| **Health** | Medical, fitness, wellness | "Schedule dentist appointment", "Renew gym membership" |
| **Errands** | One-off errands and pickups | "Pick up Too Good To Go order", "Drop off dry cleaning" |
| **Chores** | Recurring household tasks | "Clean kitchen", "Do laundry", "Take out trash" |
| **Projects** | Personal projects with ongoing scope | "SecondBrain: add email ingestion", "Set up home automation" |
| **General** | Catch-all for anything that doesn't fit above | "Update resume", "Research phone plans" |

### Work Item 1: Update classification prompt with Personal subcategories

**Goal:** Give the LLM clear guidance on which `sub_project` to assign for Personal tasks.

**Behavior:**
- Add a new section to `CLASSIFICATION_PROMPT` after the existing category/sub_project instructions, specifically for Personal subcategories
- The prompt addition should list each subcategory with 1-2 example task descriptions so the LLM can pattern-match
- For non-Personal categories (AT&T, PwC), sub_project behavior remains unchanged — the LLM infers from context (e.g., "AI Receptionist")
- If a Personal task doesn't clearly fit any subcategory, the LLM should use "General"

**Prompt addition (to be inserted into CLASSIFICATION_PROMPT):**
```
When category is "Personal", assign sub_project from these subcategories:
- "Family": family logistics, visits, coordination with family members
- "Rachel": anything specific to Rachel — relationship, proposal, dates, gifts for Rachel
- "Gifts": gifts for anyone (birthdays, holidays, occasions) — EXCEPT gifts for Rachel (use "Rachel")
- "Health": medical appointments, fitness, wellness
- "Errands": one-off errands, pickups, drop-offs
- "Chores": recurring household tasks (cleaning, laundry, etc.)
- "Projects": personal projects with ongoing scope (e.g., SecondBrain, home automation)
- "General": anything that doesn't clearly fit above
If unsure between subcategories, prefer "General" over guessing wrong.
```

**Files:** `src/secondbrain/scripts/inbox_processor.py` (CLASSIFICATION_PROMPT)

### Work Item 2: Add PERSONAL_SUB_PROJECTS constant

**Goal:** Define the subcategory list as a constant alongside `TASK_CATEGORIES` for maintainability and potential future use in validation.

**Behavior:**
- Add a `PERSONAL_SUB_PROJECTS` list constant near `TASK_CATEGORIES` (line 26)
- Use this constant in the prompt and in validation
- Note: unlike `_CATEGORY_OPTIONS` (which is a simple `join()`), the Personal subcategory prompt block needs descriptive text per subcategory. Define the constant as a dict mapping subcategory name to a short description, and build the prompt section from it.
- This makes it easy to add/remove subcategories later without editing the prompt string directly

**Files:** `src/secondbrain/scripts/inbox_processor.py`

### Work Item 3: Normalize Personal sub_project after classification

**Goal:** Ensure the LLM returns valid subcategories and gracefully handle unexpected values.

**Behavior:**
- Create a **new** `_normalize_personal_subcategory(classification: dict) -> None` function — do NOT modify `_validate_classification()`, which is a boolean structural validator and should not mutate data
- Call `_normalize_personal_subcategory()` in `_classify_with_retry()` after `_validate_classification()` passes
- When `category == "Personal"` and `sub_project` is set, check if it's in `PERSONAL_SUB_PROJECTS`
- If not recognized, log a warning and remap `sub_project` to `"General"` (don't reject the classification)
- For non-Personal categories, sub_project is left unchanged (any value is accepted since work projects are dynamic)

**Files:** `src/secondbrain/scripts/inbox_processor.py`

## Implementation Order

1. WI2 (constant) — no dependencies
2. WI1 (prompt update) — uses constant from WI2
3. WI3 (validation) — uses constant from WI2

All three are small and can reasonably be done in one pass.

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| Subcategories for AT&T or PwC | Those already have organic sub-projects (AI Receptionist, Welcome Agent) that the LLM infers from context |
| Frontend UI changes for subcategories | The task views already render sub-projects — no changes needed |
| Retroactive re-categorization of existing Personal tasks | Existing tasks in daily notes will keep their current flat "Personal" category; new tasks going forward will get subcategories. A retroactive fix could be done separately if desired. |
| Making subcategories user-configurable via settings | Over-engineering for now — edit the constant when needed |

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM miscategorizes tasks (e.g., "Errands" vs "Chores") | Low — cosmetic, user can reassign via task update API | Clear prompt examples; "General" as safe fallback |
| Existing "Personal" tasks without sub_project look different from new ones | Low — they'll just show at the top of the Personal section without a sub-heading | Acceptable UX; can backfill later if desired |
| LLM invents subcategory names not in the list | Low | Validation in WI3 remaps unknown values to "General" |

## Testing

**Automated:**
- Unit test: classification with Personal task assigns valid sub_project
- Unit test: validation remaps unknown Personal sub_project to "General"
- Unit test: non-Personal tasks are not affected by new validation
- Integration test: captured note with personal tasks produces correct `#### Sub-project` headings in daily note

**Manual QA:**
- Capture a note with mixed personal tasks ("pick up groceries", "schedule dentist", "work on SecondBrain")
- Verify each task gets the correct subcategory in today's daily note
- Run task sync and verify All Tasks.md shows subcategory groupings under Personal

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| 8 subcategories (not fewer) | The user has diverse personal task types; lumping "Health" and "Errands" or "Family" and "Gifts" would lose the value of subcategorization |
| Rachel as its own subcategory (not under Family) | Rachel-specific tasks (proposal, dates, relationship) are a distinct high-frequency category; keeps Family for broader family logistics |
| Projects as a Personal subcategory (not a top-level category) | The user works on personal projects "a decent amount" but they're still personal in nature. Keeps the top-level categories clean (AT&T, PwC, Personal = work/work/life). If the user later wants Projects elevated to top-level, that's a simple config change. |
| Prompt-based approach (not rule-based) | The LLM already does category assignment well for AT&T/PwC — extending the same pattern to Personal subcategories is consistent and flexible |
| Validation remaps to "General" instead of rejecting | A slightly wrong subcategory is better than a failed classification that drops the entire capture |
| Normalization is a separate function from `_validate_classification()` | `_validate_classification()` is a pure boolean structural check — adding mutation (remapping sub_project) would break single-responsibility. A separate `_normalize_personal_subcategory()` keeps concerns clean. |

## Known Minor Issues

| # | Issue | Notes |
|---|-------|-------|
| 1 | The prompt block needs descriptive text per subcategory, not just names — can't be a simple `join()` like `_CATEGORY_OPTIONS` | Implementation should build the prompt section from a dict constant `{name: description}` so the examples stay alongside the names |
| 2 | Existing Personal tasks without `sub_project` will appear at the top of the Personal section without a sub-heading | Acceptable UX — can backfill later if desired |
