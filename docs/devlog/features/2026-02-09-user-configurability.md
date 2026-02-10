# Feature: User Configurability

**Date:** 2026-02-09
**Branch:** main

## Summary

Consolidated all personal/branding configuration into two clearly labeled files so a new user can clone the repo and customize it by editing just two files plus two static JSON files. Frontend branding (app name, user name, initial) lives in `config.ts`; vault layout, task categories, and living documents live at the top of `inbox_processor.py`.

## Problem / Motivation

SecondBrain was hardcoded to one user's vault layout, task categories, and branding. Personal values like "Brent OS", "Brent", "AT&T", "PwC", and folder names like `00_Daily` were scattered across ~10 files. A technical user cloning the repo would have to hunt through components, prompts, and routing logic to find and change all of them.

## Solution

Three independent changes, each leaving the system working after completion:

1. **Frontend branding config** (`frontend/src/lib/config.ts`) — single file exporting `APP_NAME`, `USER_NAME`, `USER_INITIAL`. Imported by `layout.tsx`, `Sidebar.tsx`. `ChatProvider.tsx` uses a stable static localStorage key (`"secondbrain-provider"`) instead of deriving it from the app name.

2. **Inbox processor constants** — added a clearly delimited `USER CONFIGURATION` section at the top of `inbox_processor.py` with `TASK_CATEGORIES`, `LIVING_DOCUMENTS`, and `VAULT_FOLDERS`. Categories are interpolated into the classification prompt via f-string helpers. Vault folder names are referenced via `VAULT_FOLDERS[...]` throughout routing logic.

3. **README setup section** — 5-step guide for new users covering env, vault folders, branding, categories, and manifest.

## Files Modified

**Frontend (branding config):**
- `frontend/src/lib/config.ts` — NEW: APP_NAME, USER_NAME, USER_INITIAL
- `frontend/src/app/layout.tsx` — import APP_NAME for page title
- `frontend/src/components/layout/Sidebar.tsx` — import all 3 config values
- `frontend/src/components/providers/ChatProvider.tsx` — stable static PROVIDER_KEY

**Backend (inbox constants):**
- `src/secondbrain/scripts/inbox_processor.py` — TASK_CATEGORIES, VAULT_FOLDERS, improved LIVING_DOCUMENTS comments, f-string classification prompt

**Docs:**
- `README.md` — added "Customize for Your Vault" section, updated implementation status table
- `docs/ROADMAP.md` — marked Phases 5, 5.5, 5.7 as done
- `CLAUDE.md` — updated implementation phases list

## Key Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| **Config file, not env vars for frontend** | Next.js `NEXT_PUBLIC_*` vars require build-time injection. A simple TypeScript constants file is more discoverable and doesn't require env var plumbing for a self-hosted tool. |
| **Constants in Python file, not YAML** | For <5 config values, constants at the top of the file are more discoverable than an external config system. No parsing dependency needed. |
| **Static PROVIDER_KEY instead of derived** | Code-simplifier caught that deriving the localStorage key from APP_NAME would silently lose saved preferences if someone changed their app name. A stable key (`"secondbrain-provider"`) is safer. |
| **f-string prompt with helper variables** | `_CATEGORY_OPTIONS`, `_CATEGORY_LIST`, `_FIRST_CATEGORY`, `_LIVING_DOCS_PROMPT` are computed once at module load. Keeps the prompt template readable while making categories dynamic. |
| **manifest.json and package.json left as manual edits** | These are static files not worth build-time injection. A comment in config.ts points users to them. |

## Patterns Established

- **Frontend config pattern**: New pages/components that reference branding should import from `@/lib/config` rather than hardcoding values.
- **Inbox processor config pattern**: New vault-specific constants (folders, categories, document mappings) should go in the `USER CONFIGURATION` section at the top of `inbox_processor.py`.
- **Prompt interpolation pattern**: Use module-level helper variables (prefixed with `_`) to pre-compute prompt fragments from config constants. Use f-strings with `{{` / `}}` for literal JSON braces.

## Testing

- All 220 existing tests pass (`make check` — lint, format, mypy, pytest)
- Frontend builds successfully (`npx next build`)
- Frontend service restarted and returns HTTP 200
- Pre-push hooks pass (full test suite)

## Future Considerations

- If the project gains more config points, a dedicated `config.yaml` or settings UI might be warranted, but for now the two-file approach is proportionate.
- The `LIVING_DOCUMENTS` paths still reference folder names directly (e.g., `"10_Notes/Grocery List.md"`) rather than using `VAULT_FOLDERS`. This is intentional — they're in the same config section and meant to be edited together.
- `task_aggregator.py` has a comment mentioning "AT&T", "PwC", "Personal" as docstring examples. The spec noted this is not a behavioral dependency, so it was left as-is.
