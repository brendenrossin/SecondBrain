# Feature: Quick Capture

**Date:** 2026-02-09
**Branch:** main

## Summary

Added a minimal quick capture system — a `POST /api/v1/capture` endpoint and a `/capture` frontend page — that lets you get thoughts into the system in under 10 seconds from any device via Tailscale. Captured text is written as a timestamped Markdown file to `Inbox/` and processed by the inbox processor on the next sync.

## Problem / Motivation

Getting ideas into SecondBrain required either opening Obsidian directly or dictating into Apple Notes and hoping the daily sync picks it up. This added friction, especially from a phone, and made it easy to lose thoughts between capture and processing.

## Solution

Thin full-stack feature with minimal moving parts:

- **Backend:** Single `POST /api/v1/capture` endpoint that writes `capture_YYYY-MM-DD_HHMMSS.md` to `Inbox/`. No LLM, no database, no dependencies beyond `get_settings()` for the vault path. Pydantic validation enforces 1-10000 char limits.
- **Frontend:** `/capture` page with a glass-card textarea, Cmd/Ctrl+Enter to send, character count, and success/error feedback. 3-second auto-reset after success for rapid sequential captures.
- **Integration:** Files in `Inbox/` are picked up by the existing inbox processor on the next hourly sync (or manual `make daily-sync`), which classifies, segments, extracts tasks, and routes to the appropriate vault folder.

## Files Modified

**Backend:**
- `src/secondbrain/api/capture.py` — NEW: capture endpoint
- `src/secondbrain/main.py` — register capture router
- `src/secondbrain/models.py` — CaptureRequest, CaptureResponse

**Frontend:**
- `frontend/src/components/capture/CaptureForm.tsx` — NEW: capture form component
- `frontend/src/app/(dashboard)/capture/page.tsx` — NEW: route page
- `frontend/src/lib/api.ts` — captureText() function
- `frontend/src/lib/types.ts` — CaptureResponse interface
- `frontend/src/components/layout/Sidebar.tsx` — Capture nav item with Feather icon

**Tests:**
- `tests/test_capture_api.py` — NEW: 6 tests (success, dir creation, no vault path, empty/missing/long text)

**Docs:**
- `docs/ROADMAP.md` — Phase 6.5 marked done

## Key Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| **No LLM at capture time** | Classification happens during inbox processing, not capture. Keeps capture instant (<100ms) and works even if LLM is down. |
| **Plain text files, not database** | Inbox processor already handles `.md` files. No new storage layer needed. Files are the interface. |
| **No frontmatter on captured files** | The inbox processor adds frontmatter during classification. Raw text is the simplest input format. |
| **UTC timestamps in filenames** | Avoids timezone ambiguity. Inbox processor doesn't care about filename format. |
| **Capture in Core nav, not Tools** | Quick capture is a primary action (like Chat), not an occasional tool (like Admin). Placed between Chat and Tasks. |
| **3-second auto-reset** | After success, the form resets to idle so the user can immediately capture another thought. Timer is cleaned up on unmount to prevent React state updates on unmounted components. |
| **10KB max text limit** | Generous for dictated/typed capture; prevents accidental paste of entire documents. |

## Patterns Established

- **Lightweight API endpoints:** Not everything needs dependency injection. `get_settings()` is `@lru_cache` — calling it directly (vs `Depends()`) is fine for simple read-only endpoints.
- **File-as-interface pattern:** Write to `Inbox/` and let the existing processor handle it. No coupling between capture and classification.

## Testing

- 6 backend tests covering success, directory creation, missing config, and validation edge cases
- `make check` passes (226 tests, lint, types all clean)
- Frontend builds successfully
- Manual verification: POST to `/api/v1/capture` writes file to `Inbox/`

## Future Considerations

- **Immediate processing option:** Could add `?process=true` query param to trigger inline inbox processing instead of waiting for next sync. Would increase latency but give instant feedback.
- **Mobile-optimized layout:** The current page works on mobile via Tailscale but could benefit from a larger touch target and simplified layout for phone-only use.
- **Shortcut/API key:** For programmatic capture from Alfred, iOS Shortcuts, or CLI tools. Currently relies on Tailscale for auth, which is sufficient.
