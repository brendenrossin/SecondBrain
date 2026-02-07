# Feature: Brent OS — Next.js Frontend Dashboard

**Date:** 2026-02-06
**Branch:** main

## Summary

Replaced the Gradio UI with a modern Next.js 15 dashboard called "Brent OS". Desktop shows a three-panel layout (nav sidebar + main content + persistent chat panel). Mobile uses bottom tab navigation. Dark theme inspired by Linear.app. Backend extended with 3 new API route groups (tasks, conversations, provider toggle on /ask).

## Problem / Motivation

The Gradio UI was functional but limited — no persistent chat panel alongside other views, no task visualization, no calendar, and poor mobile experience. A custom frontend enables a desktop-class dashboard with simultaneous chat + tasks/calendar, proper mobile responsiveness, and PWA installability.

## Solution

Built a Next.js 15 App Router frontend in `frontend/` using TypeScript, Tailwind CSS v4, and shadcn/ui-style components. API calls proxy through Next.js rewrites to the existing FastAPI backend at `localhost:8000`, avoiding CORS. The backend was extended with:

- `provider` field on `AskRequest` for runtime OpenAI/Ollama selection
- Conversation list/detail/delete API endpoints
- Task aggregation API endpoints (reusing `task_aggregator.py` with TTL caching)

## Files Modified

**Backend (modified):**
- `src/secondbrain/models.py` — Added `TaskResponse`, `ConversationSummary`, `provider` field on `AskRequest`
- `src/secondbrain/api/ask.py` — Runtime provider selection, extracted `_build_citations()` helper
- `src/secondbrain/stores/conversation.py` — Added `list_conversations()` method
- `src/secondbrain/main.py` — Registered conversations + tasks routers
- `Makefile` — Added `frontend-install`, `frontend-dev`, `frontend-build`, `dev-all` targets

**Backend (created):**
- `src/secondbrain/api/conversations.py` — GET/DELETE conversation endpoints
- `src/secondbrain/api/tasks.py` — Task list, upcoming, categories endpoints with 60s TTL cache

**Frontend (created — all under `frontend/`):**
- Project config: `package.json`, `tsconfig.json`, `next.config.ts`, `postcss.config.mjs`
- Root layout: `src/app/layout.tsx`, `src/app/globals.css` (CSS variables for dark theme)
- Dashboard shell: `src/app/(dashboard)/layout.tsx`, `page.tsx` (redirects to /tasks)
- Pages: `chat/page.tsx`, `tasks/page.tsx`, `calendar/page.tsx`, `insights/page.tsx`
- API client: `src/lib/api.ts` (typed fetch wrappers + SSE stream parser), `types.ts`, `utils.ts`
- Layout: `AppShell.tsx` (3-panel + resizable chat), `Sidebar.tsx`, `MobileNav.tsx`
- Chat: `ChatPanel.tsx`, `ChatMessages.tsx`, `ChatMessage.tsx`, `ChatInput.tsx`, `CitationsList.tsx`, `CitationCard.tsx`, `StreamingIndicator.tsx`, `ConversationList.tsx`, `ProviderToggle.tsx`
- State: `ChatProvider.tsx` (React context for chat state + streaming)
- Tasks: `TaskTree.tsx`, `TaskCategory.tsx`, `TaskSubProject.tsx`, `TaskItem.tsx`, `TaskFilters.tsx`, `DueBadge.tsx`
- Calendar: `WeeklyAgenda.tsx`, `WeekNav.tsx`, `DaySection.tsx`, `AgendaTask.tsx`, `OverdueSection.tsx`
- Polish: `ErrorBoundary.tsx`, `useKeyboardShortcuts.ts`
- PWA: `public/manifest.json`, `public/favicon.png`

## Key Decisions & Trade-offs

1. **Next.js rewrites instead of CORS** — All `/api/v1/*` requests proxy to FastAPI. No CORS config needed, simpler deployment, and the frontend can be served from the same origin.

2. **POST-based SSE streaming** — The `/ask/stream` endpoint uses POST (not GET), so `EventSource` API can't be used. Instead, `fetch()` + `ReadableStream` reader parses SSE events manually. Works reliably with citations→tokens→done event sequence.

3. **Provider selection at runtime, not startup** — Rather than injecting reranker/answerer via FastAPI `Depends`, the `/ask` endpoints call `get_reranker()` / `get_local_reranker()` based on `request.provider`. This means the provider can change per-request without server restart.

4. **Task API reuses existing `task_aggregator.py`** — No new data store. The API calls `scan_daily_notes()` + `aggregate_tasks()` directly with a 60-second TTL cache. Simple, no migration needed, and daily notes don't change that frequently.

5. **Chat panel always visible on desktop** — The persistent right panel means you can browse tasks/calendar while chatting. Width is resizable (320-600px) and persisted to localStorage. A ref-based approach avoids stale closure bugs during drag.

6. **Tailwind v4 with CSS variables** — Theme colors defined as CSS variables in `globals.css` using `@theme` directive. Components reference `bg-bg`, `text-text-muted`, `border-border` etc. consistently.

## Patterns Established

- **Component organization**: `components/{feature}/` directories (chat, tasks, calendar, layout, providers)
- **State management**: React Context for cross-cutting state (ChatProvider), local state for view-specific concerns
- **API client**: Typed wrappers in `lib/api.ts`, types mirroring Pydantic models in `lib/types.ts`
- **Styling**: `cn()` utility (clsx + tailwind-merge) for conditional classes, never template literal concatenation
- **Dark theme**: All colors via CSS variables, consistent naming (`bg`, `surface`, `border`, `text`, `text-muted`, `text-dim`, `accent`)
- **Backend API caching**: Simple dict-based TTL cache for expensive aggregation endpoints

## Testing

- All 156 existing backend tests pass (`make test`)
- Frontend builds cleanly (`next build` — 0 errors, 0 warnings)
- Ruff lint passes on all modified/new Python files
- TypeScript compiles with strict mode enabled
- Manual verification: `make dev-all` starts both servers, UI loads at localhost:3000

## Future Considerations

- **Task completion from UI** — Currently read-only. Would need a PATCH endpoint to toggle task completion and write back to daily notes.
- **Real-time updates** — Task/conversation lists don't auto-refresh. Could add polling or WebSocket for live updates.
- **Insights page** — Currently a placeholder. Will connect to metadata extraction and suggestion engine from Phase 3.
- **Service worker** — PWA manifest exists but no service worker for offline caching yet.
- **Authentication** — No auth on the frontend. Phase 4 (secure remote access) will add passkeys/WebAuthn.
