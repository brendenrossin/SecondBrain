# Implementation Prompt: Configurable Categories UI

## Feature Spec

Read `docs/features/configurable-categories-ui.md` for full requirements. This prompt tells you exactly what to build and where.

## Implementation Order

1. **WI1: Settings file and reader** (no dependencies)
2. **WI2: Settings API** (depends on WI1)
3. **WI3: Inbox processor** (depends on WI1, can parallel with WI2)
4. **WI4: Settings UI** (depends on WI2)
5. **WI5: Branding defaults** (independent)

WI2 and WI3 can be done in parallel after WI1. WI5 can be done anytime.

---

## WI1: Settings File and Reader

**Create `src/secondbrain/settings.py`** (new file):

```python
DEFAULT_SETTINGS = {
    "categories": [
        {
            "name": "Work",
            "sub_projects": {},
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
                "General": "anything that doesn't clearly fit above",
            },
        },
    ]
}
```

Functions to implement:
- `load_settings(data_path: Path) -> dict` — reads `data_path / "settings.json"`. If missing or unparseable, returns `DEFAULT_SETTINGS` and writes the defaults file.
- `save_settings(data_path: Path, settings: dict) -> None` — writes JSON with `json.dump(settings, f, indent=2)`. Use atomic write pattern: write to temp file then `os.replace()` to avoid partial reads.

The settings file lives in `data/` alongside SQLite databases and ChromaDB. It is NOT in the vault.

---

## WI2: Settings API Endpoints

**Create `src/secondbrain/api/settings.py`** (new file):

Follow the existing router pattern from other API files (e.g., `src/secondbrain/api/tasks.py`):

```python
from fastapi import APIRouter
router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
```

Endpoints:
- `GET /api/v1/settings/categories` — calls `load_settings(settings.data_path)`, returns the `categories` list
- `PUT /api/v1/settings/categories` — accepts a JSON body with a `categories` list, validates each entry has:
  - `name`: non-empty string
  - `sub_projects`: dict of string→string (can be empty `{}`)
  - Reject with 422 if validation fails
  - On success: calls `save_settings()` and returns the updated categories list

**Modify `src/secondbrain/main.py`**:
- Add import: `from secondbrain.api.settings import router as settings_router` (line ~24)
- Add registration: `app.include_router(settings_router)` (line ~67)

Use `get_settings()` to get `data_path` (same pattern as other routes). The settings file is re-read on each API call — no caching needed.

---

## WI3: Inbox Processor Reads from Settings File

**Modify `src/secondbrain/scripts/inbox_processor.py`**:

### Replace hardcoded constants with dynamic loading

1. **Remove `TASK_CATEGORIES` constant** (line 26) — replace with a function:
   ```python
   def _load_categories(data_path: Path) -> list[str]:
       settings = load_settings(data_path)
       return [c["name"] for c in settings.get("categories", [])]
   ```

2. **Remove `PERSONAL_SUB_PROJECTS` constant** (lines 28-39) — replace with a function:
   ```python
   def _load_all_sub_projects(data_path: Path) -> dict[str, dict[str, str]]:
       """Return {category_name: {sub_project_name: description}} for all categories with sub_projects."""
       settings = load_settings(data_path)
       return {
           c["name"]: c["sub_projects"]
           for c in settings.get("categories", [])
           if c.get("sub_projects")
       }
   ```

3. **Build the classification prompt dynamically** — the current `CLASSIFICATION_PROMPT` is a module-level f-string (lines 102-171). It must be built per-classification because settings can change between runs. Create a helper function:
   ```python
   def _build_classification_prompt(data_path: Path) -> str:
       categories = _load_categories(data_path)
       all_sub_projects = _load_all_sub_projects(data_path)

       category_options = " | ".join(f'"{c}"' for c in categories)
       category_list = ", ".join(categories)
       first_category = categories[0] if categories else "Work"

       # Build sub_project prompt for ALL categories that have them
       sub_project_lines = []
       for cat_name, subs in all_sub_projects.items():
           sub_project_lines.append(f"\nFor category \"{cat_name}\", sub_project options:")
           for name, desc in subs.items():
               sub_project_lines.append(f'- "{name}": {desc}')
       sub_project_prompt = "\n".join(sub_project_lines)

       # ... rest of prompt construction using these variables
   ```
   - The prompt currently uses `_CATEGORY_OPTIONS`, `_CATEGORY_LIST`, `_FIRST_CATEGORY`, and `_PERSONAL_SUB_PROMPT` (lines 90-100). Replace all of these with the dynamic equivalents.
   - Call `_build_classification_prompt(data_path)` inside `_classify_with_retry()` instead of referencing the module-level `CLASSIFICATION_PROMPT`.

4. **Rename `_normalize_personal_subcategory()` to `_normalize_subcategory()`** — generalize it to check sub_projects for ANY category that has configured sub_projects:
   ```python
   def _normalize_subcategory(classification: dict[str, Any], data_path: Path) -> None:
       all_sub_projects = _load_all_sub_projects(data_path)
       for task in classification.get("tasks", []):
           cat = task.get("category")
           sub = task.get("sub_project")
           if cat and sub and cat in all_sub_projects:
               valid_subs = all_sub_projects[cat]
               if sub not in valid_subs:
                   fallback = "General" if "General" in valid_subs else sub
                   logger.warning("Unknown %s sub_project '%s', remapping to '%s'", cat, sub, fallback)
                   task["sub_project"] = fallback
       # Same for top-level
       cat = classification.get("category")
       sub = classification.get("sub_project")
       if cat and sub and cat in all_sub_projects:
           valid_subs = all_sub_projects[cat]
           if sub not in valid_subs:
               fallback = "General" if "General" in valid_subs else sub
               logger.warning("Unknown %s sub_project '%s', remapping to '%s'", cat, sub, fallback)
               classification["sub_project"] = fallback
   ```

5. **Thread `data_path` through** — `_classify_with_retry()` and `_process_single_file()` already have access to `vault_path`. Get `data_path` from `get_settings().data_path` at the top of `process_inbox()` and pass it through. Alternatively, import and call `get_settings()` inside the helper functions (simpler, since `get_settings()` is cheap).

### Important: Don't break `_validate_classification()`

`_validate_classification()` (around line 266) is a pure boolean check that validates the JSON structure — it does NOT reference `TASK_CATEGORIES`. Leave it unchanged.

---

## WI4: Settings UI Page

### Create `frontend/src/app/(dashboard)/settings/page.tsx`

Follow the admin page pattern:

```typescript
"use client";

import { Settings } from "lucide-react";
import { CategoryManager } from "@/components/settings/CategoryManager";

export default function SettingsPage() {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2.5 px-6 h-14 border-b border-border shrink-0">
        <Settings className="w-4.5 h-4.5 text-text-dim" />
        <h1 className="text-base font-bold text-text tracking-tight">Settings</h1>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <CategoryManager />
      </div>
    </div>
  );
}
```

### Create `frontend/src/components/settings/CategoryManager.tsx`

This component manages the full CRUD for categories and subcategories.

**Data model:**
```typescript
interface Category {
  name: string;
  sub_projects: Record<string, string>; // name → description
}
```

**State:**
- `categories: Category[]` — fetched from API on mount
- `expandedCategory: string | null` — which category is expanded to show subcategories
- `editingCategory: string | null` — which category name is being inline-edited
- `newCategoryName: string` — input for adding a new category

**Behavior:**
- On mount: `GET /api/v1/settings/categories` → set state
- Add category: append `{name, sub_projects: {}}` → PUT to API
- Delete category: confirmation dialog → remove from list → PUT to API
- Edit category name: inline text input → update in list → PUT to API
- Expand category: show subcategories list with add/edit/delete
- Add subcategory: name + description inputs → add to sub_projects → PUT
- Delete subcategory: confirmation dialog → remove from sub_projects → PUT
- Edit subcategory: inline inputs → update in sub_projects → PUT

**Save pattern:** Every mutation PUTs the full categories list to the API immediately (same auto-save pattern as task status changes — no "Save" button).

**Confirmation dialogs for delete:**
- Category: "Delete [name]? Existing tasks in this category will become Uncategorized."
- Subcategory: "Delete [name]? Existing tasks will remain under [category] without a subcategory."

**Styling:** Follow the glass-card design system. Use Tailwind classes matching existing components. Refer to `AdminDashboard.tsx` for stat card patterns and layout conventions.

### Modify `frontend/src/components/layout/Sidebar.tsx`

1. Add to `NAV_COLORS` map (around line 22):
   ```typescript
   "/settings": {
     icon: "text-zinc-400",
     iconActive: "text-zinc-200",
     bgActive: "bg-zinc-500/10",
     borderActive: "border-zinc-500/30",
     glowActive: "shadow-[0_0_15px_rgba(161,161,170,0.08)]",
   },
   ```

2. Add to `toolsNavItems` array (around line 88):
   ```typescript
   { href: "/settings", label: "Settings", icon: Settings },
   ```
   Import `Settings` from `lucide-react`. Place it after Admin.

### Modify `frontend/src/lib/api.ts`

Add API functions:

```typescript
export interface CategoryConfig {
  name: string;
  sub_projects: Record<string, string>;
}

export async function getCategories(): Promise<CategoryConfig[]> {
  return fetchJSON(`${BASE}/settings/categories`);
}

export async function updateCategories(categories: CategoryConfig[]): Promise<CategoryConfig[]> {
  return fetchJSON(`${BASE}/settings/categories`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ categories }),
  });
}
```

---

## WI5: Update Frontend Branding Defaults

**Modify `frontend/src/lib/config.ts`** (line 8-10):

Change from:
```typescript
export const APP_NAME = "Brent OS";
export const USER_NAME = "Brent";
export const USER_INITIAL = "B";
```

To:
```typescript
export const APP_NAME = "SecondBrain";
export const USER_NAME = "User";
export const USER_INITIAL = "U";
```

The existing installation will override these back to personal branding by editing this file (same as today — it's a build-time constant).

---

## Testing Requirements

**Backend tests** — create `tests/test_settings.py`:
- `load_settings()` returns defaults when file missing
- `load_settings()` reads valid JSON correctly
- `save_settings()` writes valid JSON
- `save_settings()` → `load_settings()` round-trip
- `save_settings()` atomic write (temp file + rename)

**Inbox processor tests** — update `tests/test_inbox_processor.py`:
- `_build_classification_prompt()` includes all categories from settings
- `_build_classification_prompt()` includes sub_projects for categories that have them
- `_normalize_subcategory()` works for any category with sub_projects (not just Personal)
- `_normalize_subcategory()` remaps unknown → General when General exists
- `_normalize_subcategory()` leaves unknown as-is when no General sub_project exists

**API tests** — add to `tests/test_settings.py` or separate file:
- `GET /api/v1/settings/categories` returns defaults on fresh install
- `PUT /api/v1/settings/categories` saves and returns updated categories
- `PUT` rejects empty category name (422)
- `PUT` rejects non-dict sub_projects (422)

## What's Out of Scope — DO NOT BUILD

- Automatic recategorization when categories change
- Renaming categories in daily notes (vault modification)
- Making branding API-configurable
- Multi-user settings
- Category drag-reorder
- Settings for living documents or vault folders

## Commit Workflow

After implementation: `/test-generation` → `code-simplifier` → commit.
