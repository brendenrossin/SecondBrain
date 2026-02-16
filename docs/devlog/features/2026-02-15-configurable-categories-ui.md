# Feature: Configurable Categories UI

**Date:** 2026-02-15
**Branch:** main

## Summary

Moved task categories and subcategories from hardcoded Python constants to a user-editable JSON settings file. Added a Settings API, a Settings UI page, and updated the inbox processor to read categories dynamically. New installations now default to generic "Work" and "Personal" categories instead of personal ones.

## Problem / Motivation

Task categories (`AT&T`, `PwC`, `Personal`) and Personal subcategories (`Family`, `Rachel`, etc.) were hardcoded in `inbox_processor.py`. Anyone cloning the repo had to edit source code and restart the server to customize them. Categories created via the task UI dropdown didn't feed back into the LLM classification prompt, so new captures wouldn't auto-classify into user-created categories.

## Solution

Five work items implemented in dependency order:

1. **Settings file + reader** (`src/secondbrain/settings.py`) — `load_settings()` / `save_settings()` with atomic writes and defaults fallback. Settings stored in `data/settings.json` alongside SQLite databases.
2. **Settings API** (`src/secondbrain/api/settings.py`) — `GET /api/v1/settings/categories` and `PUT /api/v1/settings/categories` with Pydantic validation.
3. **Inbox processor** — Replaced `TASK_CATEGORIES` and `PERSONAL_SUB_PROJECTS` constants with `_load_categories()` / `_load_all_sub_projects()`. Classification prompt built dynamically per run via `_build_classification_prompt()`. `_normalize_personal_subcategory()` generalized to `_normalize_subcategory()` for any category.
4. **Settings UI** — New `/settings` page with `CategoryManager` component. Full CRUD for categories and subcategories with auto-save, inline editing, and confirmation dialogs. Added to both desktop sidebar and mobile "More" menu.
5. **Branding defaults** — Changed `config.ts` from "Brent OS" / "Brent" / "B" to "SecondBrain" / "User" / "U".

## Files Modified

**New files:**
- `src/secondbrain/settings.py` — Settings reader/writer with defaults
- `src/secondbrain/api/settings.py` — Settings API router
- `frontend/src/app/(dashboard)/settings/page.tsx` — Settings page
- `frontend/src/components/settings/CategoryManager.tsx` — Category CRUD component
- `tests/test_settings.py` — 18 tests for settings module + API

**Modified files:**
- `src/secondbrain/main.py` — Registered settings router
- `src/secondbrain/scripts/inbox_processor.py` — Dynamic category loading, prompt building, generalized subcategory normalization
- `frontend/src/lib/api.ts` — `getCategories()` / `updateCategories()` functions
- `frontend/src/lib/config.ts` — Generic branding defaults
- `frontend/src/components/layout/Sidebar.tsx` — Settings nav link + color map
- `frontend/src/components/layout/MobileNav.tsx` — Settings in More menu
- `tests/test_inbox_processor.py` — Updated tests for new function signatures, added tests for dynamic prompt building and generalized subcategory normalization

**Also fixed (pre-existing mypy errors):**
- `src/secondbrain/scripts/recategorize_tasks.py` — `Path | None` guard, `str | None` fallbacks
- `src/secondbrain/scripts/inject_tasks.py` — `Path | None` guard, `dict` type params

## Key Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| Settings in `data/settings.json`, not vault | Categories are app config, not note content. Vault stays clean. |
| Prompt built per classification, not at module level | Settings can change between inbox processor runs without server restart. |
| No automatic recategorization on settings change | Users can already reassign per-task in TaskDetailPanel. Bulk recategorization exists as one-time script. |
| Vault not modified on category delete/rename | Vault is source of truth. Old tasks keep old category headings; new captures use updated names. |
| Sub_projects stored as `{name: description}` dict | Descriptions are critical for LLM classification accuracy — without them, the model guesses what "Rachel" or "Projects" means. |
| Auto-save pattern (no Save button) | Matches existing task status toggle behavior. Every mutation PUTs immediately. |

## Patterns Established

- **Settings file pattern:** `load_settings(data_path)` / `save_settings(data_path, settings)` with atomic write (tempfile + `os.replace`). Returns defaults if file missing/corrupt.
- **Dynamic prompt construction:** Module-level constants replaced with per-call builder functions when the data can change at runtime.
- **Navigation additions:** When adding a new page, ALWAYS update both `Sidebar.tsx` (desktop) and `MobileNav.tsx` (mobile "More" menu).
- **API test pattern with `get_data_path` override:** Use `unittest.mock.patch("secondbrain.api.{module}.get_data_path")` instead of FastAPI dependency overrides, since `get_data_path()` is called directly (not injected via `Depends`).

## Testing

- 453 total tests pass (18 new in `test_settings.py`, 14 new/updated in `test_inbox_processor.py`)
- Settings unit tests: load defaults, read valid JSON, handle corrupt JSON, atomic write, round-trip
- API tests: GET defaults, PUT valid/invalid, empty name rejection, invalid sub_projects type rejection
- Inbox processor tests: dynamic prompt includes all categories/sub_projects, `_normalize_subcategory` works for any category, General fallback when exists, leaves unknown as-is when no General
- `make check` passes: lint, format, mypy (0 errors across all 58 source files), pytest

## Future Considerations

- Making branding API-configurable (currently build-time constants in `config.ts`)
- Category drag-reorder in settings UI
- Per-task category dropdown could eventually sync with settings to show only configured categories
- Living documents and vault folder structure could also move to settings if users need to customize them
