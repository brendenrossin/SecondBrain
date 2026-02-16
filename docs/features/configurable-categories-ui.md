# Configurable Categories UI — User-Defined Task Categories & Subcategories

> **Status:** Planned (Phase 8.8)
> **Estimated effort:** 3-4 days
> **Depends on:** Phase 8 (task management UI, subcategory support)

## Problem

Task categories (`AT&T`, `PwC`, `Personal`) and Personal subcategories (`Family`, `Rachel`, `Gifts`, etc.) are hardcoded as Python constants in `inbox_processor.py`. A new user cloning the repo must edit source code and restart the server to change them. This makes SecondBrain feel like a personal tool rather than a product anyone can adopt.

The per-task category/sub-project editing already works great in the UI (dropdown + "create new" in TaskDetailPanel), but the LLM classification prompt — which auto-categorizes captured notes — only knows about the hardcoded categories. New categories created via the task UI don't feed back into the classification system.

## Solution

Move category/subcategory configuration from Python constants to a JSON settings file. Add a Settings API and a Settings UI page so users can manage categories without touching code. The inbox processor reads from the settings file dynamically on each run.

**Defaults for new installations:** "Work" and "Personal" (not AT&T/PwC/Personal). Personal keeps the current subcategories as sensible examples.

### Work Item 1: Settings file and reader

**Goal:** Store categories in a JSON file that both the API and inbox processor can read.

**Behavior:**
- Create `data/settings.json` with this schema:
  ```json
  {
    "categories": [
      {
        "name": "Work",
        "sub_projects": {}
      },
      {
        "name": "Personal",
        "sub_projects": {
          "Family": "family logistics, visits, coordination with family members",
          "Rachel": "anything specific to Rachel — relationship, proposal, dates, gifts for Rachel",
          "Gifts": "gifts for anyone (birthdays, holidays, occasions)",
          "Health": "medical appointments, fitness, wellness",
          "Errands": "one-off errands, pickups, drop-offs",
          "Chores": "recurring household tasks (cleaning, laundry, etc.)",
          "Projects": "personal projects with ongoing scope",
          "General": "anything that doesn't clearly fit above"
        }
      }
    ]
  }
  ```
- Create `src/secondbrain/settings.py` with:
  - `load_settings(data_path: Path) -> dict` — reads the JSON file, returns parsed dict. If file doesn't exist, returns DEFAULT_SETTINGS and writes the defaults file.
  - `save_settings(data_path: Path, settings: dict) -> None` — writes the JSON file with pretty-printing.
  - `DEFAULT_SETTINGS` — the default categories above.
- The settings file lives in `data/` alongside other application state (SQLite databases, ChromaDB). It is NOT in the vault — categories are application config, not note content.

**Files:** `src/secondbrain/settings.py` (new), `data/settings.json` (created on first read)

### Work Item 2: Settings API endpoints

**Goal:** CRUD API for categories that the frontend can call.

**Behavior:**
- `GET /api/v1/settings/categories` — Returns the current categories list from `data/settings.json`
- `PUT /api/v1/settings/categories` — Replaces the full categories list. Validates that each category has a `name` (non-empty string) and `sub_projects` (dict of name→description, can be empty). Writes to `data/settings.json`.
- Response format matches the JSON schema above.
- The settings file is re-read on each API call (no caching needed — it's a tiny file read once per request at most).

**Files:** `src/secondbrain/api/settings.py` (new), `src/secondbrain/main.py` (register router)

### Work Item 3: Inbox processor reads from settings file

**Goal:** The LLM classification prompt uses the user's configured categories instead of hardcoded constants.

**Behavior:**
- Replace `TASK_CATEGORIES` constant with a function call: `_load_categories(data_path)` that calls `load_settings()` and extracts the category names list.
- Replace `PERSONAL_SUB_PROJECTS` constant with a function call that extracts sub_projects for each category that has them.
- The `CLASSIFICATION_PROMPT` must be built dynamically inside `process_inbox()` (or a helper called per classification), not at module level. This is because the settings can change between runs.
- The prompt should list ALL categories with their sub-projects (not just Personal). If "Work" has sub-projects like "Project Alpha", those appear in the prompt too.
- `_normalize_personal_subcategory()` becomes `_normalize_subcategory()` — checks sub_projects for ANY category that has configured sub_projects, not just "Personal". Unknown sub_projects still remap to "General" if a "General" sub_project exists for that category, otherwise they're left as-is.

**Files:** `src/secondbrain/scripts/inbox_processor.py`

### Work Item 4: Settings UI page

**Goal:** A `/settings` page where users manage categories and subcategories.

**Behavior:**
- Add a `/settings` route and navigation link in the sidebar (gear icon, below Admin)
- **Category list:** Shows all categories with their subcategory count. Each has edit (pencil) and delete (trash) actions.
- **Add category:** A text input + button at the bottom of the list. Adds a new category with empty sub_projects.
- **Category detail (expand/inline):** When a category is expanded or clicked, shows its subcategories as a list of `name: description` entries. Each subcategory has edit and delete actions.
- **Add subcategory:** Text input for name + description within the expanded category view.
- **Delete category:** Confirmation dialog: "Delete [category]? Existing tasks in this category will become Uncategorized." On confirm, removes from settings file. Does NOT modify daily notes — existing tasks keep their old category heading in the vault but won't match any configured category. The user can manually reassign via the task detail panel.
- **Delete subcategory:** Confirmation dialog: "Delete [subcategory]? Existing tasks will remain under [category] without a subcategory." Same approach — vault is not modified, just the config.
- **Edit category/subcategory name:** Inline text input. Only updates the settings file — does NOT rename in daily notes. New captures use the new name; old tasks keep the old name until manually reassigned.
- **Save is automatic:** Changes are PUT to the API immediately on each add/edit/delete action (same pattern as task status changes — no "Save" button).
- **First-time experience:** If no settings file exists, the defaults are shown. The user can customize before their first capture.

**Files:** `frontend/src/app/(dashboard)/settings/page.tsx` (new), `frontend/src/components/settings/CategoryManager.tsx` (new), `frontend/src/components/layout/Sidebar.tsx` (add nav link), `frontend/src/lib/api.ts` (add settings API functions)

### Work Item 5: Update frontend branding defaults

**Goal:** New installations show generic branding, not "Brent OS".

**Behavior:**
- Change defaults in `frontend/src/lib/config.ts`:
  ```typescript
  export const APP_NAME = "SecondBrain";
  export const USER_NAME = "User";
  export const USER_INITIAL = "U";
  ```
- The existing installation can override these back to "Brent OS" by editing the config file (same as today).
- Note: Making branding itself API-configurable is deferred — it requires a frontend rebuild, so a config file is appropriate. The settings page could eventually include a "Branding" section that writes to `config.ts` and triggers a rebuild, but that's over-engineering for now.

**Files:** `frontend/src/lib/config.ts`

## Implementation Order

1. WI1 (settings file + reader) — no dependencies
2. WI2 (settings API) — depends on WI1
3. WI3 (inbox processor) — depends on WI1
4. WI4 (settings UI) — depends on WI2
5. WI5 (branding defaults) — independent, can be done anytime

WI2 and WI3 can be done in parallel after WI1.

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| Automatic recategorization when categories change | Users can already reassign per-task in the TaskDetailPanel. Not worth the complexity. |
| Renaming categories in daily notes | Vault modification is risky. New captures use new names; old tasks keep old names. |
| Making branding API-configurable | Requires frontend rebuild. Config file is appropriate for build-time constants. |
| Multi-user settings | Single-user tool. One settings file. |
| Settings for living documents or vault folders | Low-change-frequency config. Keep as Python constants with clear comments. Can be added to settings UI later if needed. |
| Category ordering in the settings UI | Alphabetical sort is fine. User can't drag-reorder categories. |

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Settings file gets corrupted/deleted | Low — inbox processor falls back to defaults | `load_settings()` returns DEFAULT_SETTINGS if file is missing or unparseable |
| Prompt gets too long with many categories/subcategories | Low — even 10 categories with 5 subcategories each is < 500 tokens | Log prompt token count at DEBUG level |
| Categories in vault don't match settings after edits | Expected — by design. Old tasks keep old category headings. | User reassigns via task detail panel. Document this in the UI with a note. |
| Race condition: settings file written by API while inbox processor reads it | Very low — hourly cron vs. rare settings edits | JSON write is atomic (write to temp file + rename). Python's `json.load()` handles partial reads gracefully. |

## Testing

**Automated:**
- Unit test: `load_settings()` returns defaults when file missing
- Unit test: `load_settings()` reads valid JSON correctly
- Unit test: `save_settings()` writes valid JSON
- Unit test: `save_settings()` → `load_settings()` round-trip
- Unit test: inbox processor builds correct prompt from settings
- Unit test: `_normalize_subcategory()` works for any category with sub_projects
- API test: `GET /api/v1/settings/categories` returns defaults on fresh install
- API test: `PUT /api/v1/settings/categories` saves and returns updated categories
- API test: `PUT` rejects invalid input (empty name, non-dict sub_projects)

**Manual QA:**
- Fresh install: settings page shows "Work" and "Personal" defaults
- Add a new category → capture a note → verify LLM classifies into it
- Delete a category → verify existing tasks still visible (as "old" category) and new captures don't use it
- Add subcategory → capture a personal task → verify it gets the subcategory

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| `data/settings.json` not vault | Categories are application config, not note content. Vault stays clean for markdown notes. |
| No recategorization on change | Users can already reassign per-task in the UI. Bulk recategorization is a rare one-time need (we already have `recategorize_tasks.py` for that). |
| Prompt built dynamically per run, not at module level | Settings can change between inbox processor runs. Module-level constants would require server restart. |
| Defaults are "Work" + "Personal" | Generic enough for any user. The current AT&T/PwC categories are personal to one user. |
| Sub_projects stored as `{name: description}` dict | The description is used in the LLM prompt to help classification. Without descriptions, the LLM would have to guess what "Rachel" or "Projects" means. |
| Delete doesn't modify vault | Vault is source of truth — we don't auto-edit daily notes. The settings file controls what the LLM classifies INTO, not what exists in the vault. |
