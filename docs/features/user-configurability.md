# User Configurability — Making SecondBrain Cloneable

> **Status:** Planned (pre-Phase 5 cleanup)
> **Estimated effort:** 0.5–1 day
> **Depends on:** Nothing — can be done independently
> **Priority:** Do before Phase 5 so all new code follows the pattern

## Problem

SecondBrain is hardcoded to one user's vault layout, task categories, and branding. A technical user cloning the repo would need to hunt through ~10 files to find and change personal values. The fixes are small — no re-architecture needed — but the personalization points should be consolidated and clearly labeled.

## Scope

Three changes. Each is independent and leaves the system working after completion.

---

### 1. Frontend Branding Config

**Goal:** One file to change all UI branding.

**Current state:** "Brent OS" and "Brent" are scattered across 6 locations:

| File | What |
|------|------|
| `frontend/src/app/layout.tsx:5` | Page title (`"Brent OS"`) |
| `frontend/src/components/layout/Sidebar.tsx:139` | Sidebar header (`"Brent OS"`) |
| `frontend/src/components/layout/Sidebar.tsx:175` | User name (`"Brent"`) + initial (`"B"`) |
| `frontend/src/components/providers/ChatProvider.tsx:34` | localStorage key (`"brentos-provider"`) |
| `frontend/public/manifest.json:2-3` | PWA name (`"Brent OS"`, `"BrentOS"`) |
| `frontend/package.json:2` | npm package name (`"brent-os"`) |

**Change:**

Create `frontend/src/lib/config.ts`:
```typescript
/** Customize these for your installation */
export const APP_NAME = "Brent OS";
export const USER_NAME = "Brent";
export const USER_INITIAL = "B";
```

Update the 4 component/layout files to import from this config. The `manifest.json` and `package.json` stay as manual edits (they're static files, not worth build-time injection — just add a comment pointing to them).

**Do NOT use an env var.** These are build-time constants for a self-hosted tool. A config file is simpler, more discoverable, and doesn't require env var plumbing in Next.js.

---

### 2. Inbox Processor Personal Constants

**Goal:** One clearly labeled section at the top of `inbox_processor.py` for all personal config.

**Current state:** Three sets of personal data are embedded in the file:

**a) Living documents** (lines 16-21):
```python
LIVING_DOCUMENTS: dict[str, tuple[str, str]] = {
    "Grocery List": ("10_Notes/Grocery List.md", "replace"),
    "Recipe Ideas": ("10_Notes/Recipe Ideas.md", "append"),
}
```
Already a constant, but needs a better comment.

**b) Task categories** in `CLASSIFICATION_PROMPT` (lines 50-101):
- Line 57: `"category": "AT&T" | "PwC" | "Personal" | null,`
- Line 63: example `"category": "AT&T", "sub_project": "AI Receptionist"`
- Line 101: `Categories are typically: AT&T, PwC, or Personal.`

**c) Vault folder names** used in routing (lines 279-361):
- `"00_Daily"`, `"10_Notes"`, `"20_Projects"`, `"30_Concepts"`

**Change:**

Add a clearly labeled configuration section at the top of the file (after imports, before prompts):

```python
# ============================================================
# USER CONFIGURATION — Customize these for your vault
# ============================================================

# Task categories the LLM classifies dictated notes into.
# These appear in the classification prompt and determine
# how tasks are organized on the Tasks page.
TASK_CATEGORIES = ["AT&T", "PwC", "Personal"]

# Living documents: notes that get updated in-place instead
# of creating new files. Each entry maps a document name to
# (vault_path, semantics). "replace" overwrites content;
# "append" adds to the end.
LIVING_DOCUMENTS: dict[str, tuple[str, str]] = {
    "Grocery List": ("10_Notes/Grocery List.md", "replace"),
    "Recipe Ideas": ("10_Notes/Recipe Ideas.md", "append"),
}

# Vault folder structure. Change these if your Obsidian vault
# uses different folder names.
VAULT_FOLDERS = {
    "daily": "00_Daily",
    "notes": "10_Notes",
    "projects": "20_Projects",
    "concepts": "30_Concepts",
}
```

Then interpolate `TASK_CATEGORIES` into `CLASSIFICATION_PROMPT` using an f-string or `.format()`, and use `VAULT_FOLDERS[...]` in the routing logic instead of hardcoded strings.

**Do NOT create a YAML config file or external config system.** Constants in the Python file are the right level of abstraction for a single-user tool with <5 config values.

---

### 3. README Setup Section

**Goal:** A new user knows exactly what to customize after cloning.

**Change:** Add a "Setup for your vault" section to the project README (or CLAUDE.md) that says:

1. Set `SECONDBRAIN_VAULT_PATH` in `.env`
2. Create these folders in your vault: `00_Daily/`, `10_Notes/`, `20_Projects/`, `30_Concepts/`, `Inbox/`, `Tasks/`, `90_Meta/Templates/`
3. Edit `frontend/src/lib/config.ts` — set your display name
4. Edit task categories and living documents at the top of `src/secondbrain/scripts/inbox_processor.py`
5. Update `frontend/public/manifest.json` and `frontend/package.json` with your app name

That's it. Five steps, all in one place.

---

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| **Env var for display name** | Overengineered. Next.js `NEXT_PUBLIC_*` vars require build-time injection. A config file is simpler for a self-hosted tool. |
| **YAML/JSON config file for inbox settings** | Constants in the Python file are more discoverable and don't add a file parsing dependency. |
| **Plist setup script** | macOS-specific infrastructure. Technical users can find-and-replace a path. |
| **Making vault folder structure fully dynamic** | The numbered folder convention (`00_`, `10_`, `20_`, `30_`) is a reasonable standard. Constants make them changeable; a full plugin system would be over-engineering. |
| **Multi-user support** | Not a goal. This is a single-user, self-hosted tool. |

## Files Modified

| File | Action |
|------|--------|
| `frontend/src/lib/config.ts` | **Create** — branding constants |
| `frontend/src/app/layout.tsx` | Import from config |
| `frontend/src/components/layout/Sidebar.tsx` | Import from config |
| `frontend/src/components/providers/ChatProvider.tsx` | Import from config for localStorage key |
| `src/secondbrain/scripts/inbox_processor.py` | Consolidate personal constants, interpolate into prompt |
| `README.md` (or `CLAUDE.md`) | Add setup section |

## Testing

- All 174 existing tests must pass (`make check`)
- Frontend must render correctly after config import changes (visual check)
- Inbox processor tests already mock LLM calls — they should be unaffected by constant extraction
- Verify `CLASSIFICATION_PROMPT` still produces valid JSON structure after interpolation

## Implementation Notes

- Do this before Phase 5 so the morning briefing endpoint uses `VAULT_FOLDERS` constants from the start instead of hardcoding `"00_Daily"` again
- The `task_aggregator.py` comment on line 30 (`# e.g. "AT&T", "PwC", "Personal"`) is just a docstring example — not a behavioral dependency. Leave it as-is.
