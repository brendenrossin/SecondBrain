# Feature: Insights Dashboard

**Date:** 2026-02-13
**Branch:** main

## Summary

Replaced the placeholder "Coming soon" Insights page with a full vault knowledge explorer. The dashboard lets you browse note metadata, entities, key phrases, action items, and cross-note connections — all powered by existing backend APIs with zero new endpoints.

## Problem / Motivation

The Insights page was a static placeholder since Phase 3.5. The backend already had rich APIs for metadata extraction (`/metadata`, `/suggestions`, `/entities`, `/action-items`), but there was no way to explore this data in the UI. Users had to rely on raw API calls or the chat interface to discover vault structure.

## Solution

Built a purely frontend feature with three components:

1. **InsightsDashboard** — Main container with stat cards, tab switcher (Notes/Entities), and data loading via `Promise.all` across three API endpoints.
2. **NoteDetail** — Full metadata view for a selected note: summary, key phrases (pill badges), entities (grouped by type with emoji), dates, action items (priority-coded), and connections (related notes, suggested links, suggested tags fetched on-demand via `/suggestions`).
3. **EntityBrowser** — Vault-wide entity list with type filter tabs (All/People/Orgs/Products/Places), client-side deduplication, and note cross-links that switch to the Notes tab.

## Files Modified

**New components:**
- `frontend/src/components/insights/InsightsDashboard.tsx` — Main dashboard
- `frontend/src/components/insights/NoteDetail.tsx` — Note detail panel
- `frontend/src/components/insights/EntityBrowser.tsx` — Entity browser with filters
- `frontend/src/components/StatCard.tsx` — Shared stat card (extracted from AdminDashboard)
- `frontend/src/lib/constants.ts` — Shared `ENTITY_EMOJI` mapping

**Modified:**
- `frontend/src/app/(dashboard)/insights/page.tsx` — Replaced placeholder with dashboard
- `frontend/src/components/admin/AdminDashboard.tsx` — Now imports shared StatCard
- `frontend/src/lib/api.ts` — Added `listMetadata`, `listEntities`, `listActionItems`; fixed `getMetadata`/`getSuggestions` return types
- `frontend/src/lib/types.ts` — Added `EntityWithSource`, `ActionItemWithSource`
- `frontend/src/lib/utils.ts` — Added shared `extractTitle`, `extractFolder` helpers
- `docs/ROADMAP.md` — Added Phase 9.5 for Insights Dashboard

## Key Decisions & Trade-offs

- **Frontend-only implementation**: All backend APIs already existed. No new endpoints were needed, which kept the scope tight and risk low.
- **Client-side deduplication**: Entities are deduplicated in the browser (by `text|entity_type` key) rather than adding a dedup endpoint. Fine for the current scale (<200 notes), but may need server-side grouping if entity counts grow large.
- **On-demand suggestions loading**: The `/suggestions` endpoint is called per-note when selected, not prefetched for all notes. This avoids a potentially expensive N+1 load on mount but means a brief loading spinner when switching notes.
- **Responsive mobile/desktop**: Notes tab uses a side-by-side layout on desktop (2fr/3fr grid) and a show/hide toggle on mobile — selecting a note hides the list, with a back button to return.
- **Shared StatCard extraction**: The identical `StatCard` component existed in both AdminDashboard and InsightsDashboard. Extracted to a shared component to avoid drift.

## Patterns Established

- **Shared UI constants**: `frontend/src/lib/constants.ts` for cross-component constants like `ENTITY_EMOJI`. Use this for any future shared mappings.
- **Shared helper extraction**: `extractTitle` and `extractFolder` were duplicated in 3 files. Now in `utils.ts`. Any vault path manipulation should use these.
- **Shared StatCard**: `frontend/src/components/StatCard.tsx` — any dashboard needing stat cards should import from here, not redefine.
- **Tab-based dashboard pattern**: Notes/Entities tabs with cross-linking (entity click switches to Notes tab with that note selected). Follow this pattern for future dashboard tabs.

## Testing

- Frontend-only feature; verified via `npm run build` (compiles cleanly, 6.04 kB for insights page).
- Manual verification: frontend service returns 200 after rebuild and restart.
- No new backend tests needed — all APIs were already tested.

## Future Considerations

- **Wiki link map**: The feature spec mentions a "wiki link map" showing outgoing/incoming links for a note. Deferred to post-Phase 9 (link-aware retrieval) since link data isn't surfaced in the current APIs.
- **Search/filter in notes list**: Currently shows all notes alphabetically. A search box or folder filter would help at scale.
- **Pagination**: Currently fetches up to 200 notes. If the vault grows significantly, pagination or virtual scrolling would be needed.
- **Most-connected notes ranking**: The spec mentions surfacing "most-connected" notes. This requires counting incoming suggestions across all notes — a potentially expensive operation that could be added as a backend endpoint.
