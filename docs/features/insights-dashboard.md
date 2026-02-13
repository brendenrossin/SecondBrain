# Insights Dashboard — Vault Knowledge Explorer

> **Status:** Planned (Phase 9.5)
> **Estimated effort:** 3-5 days
> **Depends on:** Phase 3 (metadata extraction — already complete), Phase 9 (link-aware retrieval — for wiki link display)
> **Priority:** Medium — unlocks existing backend work that's been sitting unused

## Problem

Phase 3 built a full metadata extraction pipeline (summaries, entities, dates, action items, related notes, suggested links, suggested tags) with 6 API endpoints. The Insights page in the frontend is a "Coming soon" placeholder. All that extracted intelligence is invisible to the user.

The backend APIs have been live and working since Phase 3:
- `GET /api/v1/metadata` — all note metadata (paginated)
- `GET /api/v1/metadata/{path}` — single note detail
- `GET /api/v1/suggestions/{path}` — related notes, link suggestions, tag suggestions
- `GET /api/v1/entities?entity_type=` — all entities across vault
- `GET /api/v1/action-items` — all action items across vault

Frontend wrappers `getMetadata()` and `getSuggestions()` already exist in `api.ts` but are unused.

## Solution

Replace the placeholder with a two-panel explorer: a browsable list of all indexed notes on the left, and a detail view on the right showing metadata, connections, and suggestions for the selected note. Add vault-wide stat cards and an entity browser tab.

**No backend changes.** This is entirely frontend work consuming existing APIs.

### WI1: API Layer — Add Missing Fetch Functions

**Goal:** Wire up the remaining backend endpoints that have no frontend wrapper.

**Files:**
- Modify `frontend/src/lib/api.ts`
- Modify `frontend/src/lib/types.ts` (add entity-with-note-path type)

**Add to `api.ts`:**
```typescript
export async function listMetadata(
  offset = 0,
  limit = 200
): Promise<NoteMetadata[]> {
  return fetchJSON(`${BASE}/metadata?offset=${offset}&limit=${limit}`);
}

export async function listEntities(
  entityType?: string
): Promise<{ entities: EntityWithSource[]; total: number }> {
  const qs = entityType ? `?entity_type=${entityType}` : "";
  return fetchJSON(`${BASE}/entities${qs}`);
}

export async function listActionItems(): Promise<{
  action_items: ActionItemWithSource[];
  total: number;
}> {
  return fetchJSON(`${BASE}/action-items`);
}
```

**Add to `types.ts`:**
```typescript
export interface EntityWithSource {
  text: string;
  entity_type: string;
  confidence: number;
  note_path: string;
}

export interface ActionItemWithSource {
  text: string;
  confidence: number;
  priority: string | null;
  note_path: string;
}
```

**Also update the existing `getMetadata` and `getSuggestions` wrappers** to return typed responses instead of `Record<string, unknown>`:
```typescript
export async function getMetadata(path: string): Promise<NoteMetadata> { ... }
export async function getSuggestions(path: string): Promise<NoteSuggestions> { ... }
```

**Testing:** Verify each function returns typed data by calling them in the browser console or from the Insights component.

---

### WI2: Vault Overview — Stat Cards + Note List

**Goal:** Replace the placeholder with a real dashboard showing vault-wide stats and a browsable note list.

**Files:**
- Rewrite `frontend/src/app/(dashboard)/insights/page.tsx`
- Create `frontend/src/components/insights/InsightsDashboard.tsx`

**Page layout (follows Admin page pattern):**
```
┌──────────────────────────────────────────────────┐
│ 💡 Insights                            [Refresh] │
├──────────────────────────────────────────────────┤
│                                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐│
│  │ Notes   │ │Entities │ │ People  │ │Action  ││
│  │   16    │ │   42    │ │   12    │ │Items 8 ││
│  │extracted│ │ total   │ │         │ │high: 3 ││
│  └─────────┘ └─────────┘ └─────────┘ └────────┘│
│                                                  │
│  [Notes]  [Entities]           ← tab switcher    │
│                                                  │
│  Notes tab (default):                            │
│  ┌──────────────────────────────────────────────┐│
│  │ 📄 Q3 Planning Notes          10_Notes       ││
│  │ Budget review and timeline for Q3 project... ││
│  │ entities: Sarah, PwC  ·  2 action items      ││
│  ├──────────────────────────────────────────────┤│
│  │ 📄 Budget Allocation Framework  30_Concepts  ││
│  │ Framework for distributing budget across...  ││
│  │ entities: Finance Team  ·  0 action items    ││
│  └──────────────────────────────────────────────┘│
│                                                  │
└──────────────────────────────────────────────────┘
```

**Stat cards (reuse `StatCard` pattern from AdminDashboard):**
1. **Notes Extracted** — count of metadata entries, subtitle "X with summaries"
2. **Entities** — total entity count, subtitle with type breakdown ("12 people, 8 orgs, ...")
3. **Key Phrases** — total unique key phrases across all notes
4. **Action Items** — total count, subtitle "X high priority"

**Note list:**
- Fetch all metadata via `listMetadata(0, 200)`
- Each row shows: note title (from note_path filename), folder badge, summary (truncated to 2 lines), entity count + action item count
- Sorted alphabetically by note title
- Clicking a row selects it (highlights) and loads the detail view (WI3)
- On mobile: note list is full-width, detail view opens as a slide-over or expands inline below the selected row

**Loading state:** Skeleton cards + skeleton list rows (same pattern as Tasks page).

**Empty state:** If no metadata exists, show a message: "No notes have been extracted yet. Run `make extract` or wait for the next daily sync."

---

### WI3: Note Detail Panel

**Goal:** When a note is selected from the list, show its full metadata and suggestions.

**Files:**
- Create `frontend/src/components/insights/NoteDetail.tsx`

**Layout:**
```
┌──────────────────────────────────────┐
│ Q3 Planning Notes                    │
│ 10_Notes/Q3 Planning Notes.md       │
│ Extracted: 2026-02-10 · claude-haiku │
├──────────────────────────────────────┤
│                                      │
│ Summary                              │
│ Budget review and timeline for the   │
│ Q3 project. Key decisions around...  │
│                                      │
│ Key Phrases                          │
│ [budget] [Q3] [timeline] [review]   │
│                                      │
│ Entities                             │
│ 👤 Sarah (0.92)  🏢 PwC (0.88)     │
│ 📦 Budget Tool (0.75)               │
│                                      │
│ Dates                                │
│ 📅 2026-03-15 — deadline (0.90)     │
│ 📅 2026-02-20 — event (0.85)        │
│                                      │
│ Action Items                         │
│ ⚡ Review budget with Sarah [high]   │
│ • Send timeline to team [medium]     │
│                                      │
│ ─── Connections ───                  │
│                                      │
│ Related Notes                        │
│ 📄 Project Alpha Kickoff (0.82)     │
│    shared: Sarah, PwC               │
│ 📄 Q2 Retrospective (0.71)         │
│    shared: PwC                       │
│                                      │
│ Suggested Links                      │
│ 🔗 → Budget Allocation Framework    │
│    "budget allocation" (0.80)        │
│                                      │
│ Suggested Tags                       │
│ 🏷️ #project-management (0.85)      │
│ 🏷️ #finance (0.78)                 │
│                                      │
└──────────────────────────────────────┘
```

**Data fetching:**
- Metadata is already loaded from the list (WI2 fetches all metadata upfront)
- Suggestions are loaded on-demand when a note is selected: `getSuggestions(note_path)`
- Show a loading spinner for the Connections section while suggestions load

**Sections:**
1. **Header** — note title, full path, extraction timestamp, model used
2. **Summary** — the extracted summary text
3. **Key Phrases** — rendered as pill badges (small rounded chips, `bg-accent/10 text-accent`)
4. **Entities** — grouped by type with emoji prefix (👤 person, 🏢 org, 📦 product, 📍 place), confidence shown as subtle number
5. **Dates** — each with normalized date, type badge (deadline/event/reference), confidence
6. **Action Items** — priority indicator (⚡ high = accent color, • medium = default, ○ low = dim), text
7. **Related Notes** — from suggestions API: note title, similarity score, shared entities listed below
8. **Suggested Links** — from suggestions API: target note title, anchor text, confidence, reason
9. **Suggested Tags** — from suggestions API: tag name, confidence, source notes count

**Responsive:**
- Desktop (≥768px): note list on left (~40% width), detail panel on right (~60% width), side-by-side
- Mobile (<768px): note list is full-width. Tapping a note shows detail view full-width (back button to return to list). Use a simple state toggle, not a router change.

---

### WI4: Entity Browser Tab

**Goal:** A second tab that shows all entities across the vault, grouped and filterable by type.

**Files:**
- Create `frontend/src/components/insights/EntityBrowser.tsx`

**Layout:**
```
┌──────────────────────────────────────┐
│ [All] [People] [Orgs] [Products]    │
│                [Places]              │
├──────────────────────────────────────┤
│                                      │
│ 👤 People (12)                       │
│  Sarah — Q3 Planning, Project Alpha  │
│  Mike — Onboarding Notes             │
│  ...                                 │
│                                      │
│ 🏢 Organizations (8)                │
│  PwC — Q3 Planning, Budget Review    │
│  AT&T — Sprint Notes, Q2 Retro      │
│  ...                                 │
│                                      │
│ 📦 Products (5)                      │
│  ...                                 │
│                                      │
└──────────────────────────────────────┘
```

**Data fetching:**
- Fetch `listEntities()` (all entities)
- Client-side grouping by `entity_type`
- Client-side filtering when a type tab is selected
- Client-side deduplication: same entity text across multiple notes → group them, show note list

**Deduplication logic:**
```typescript
// Group by (entity_text, entity_type) → list of note_paths
const grouped = new Map<string, { text: string; type: string; notes: string[] }>();
```

**Each entity row shows:**
- Entity text (bold)
- List of note titles that mention it (comma-separated, truncated to 3 + "and N more")
- Confidence is the max across all mentions

**Type filter tabs:** All | People | Orgs | Products | Places
- "All" shows all types grouped with section headers
- Selecting a type shows only that type, flat list

**Clicking a note title in an entity row:** selects that note in the Notes tab and switches to it (or scrolls to it). Simple state lift — pass a callback up to the parent `InsightsDashboard` that sets the selected note path and switches to the Notes tab.

---

### WI5: Tab Switcher + Component Wiring

**Goal:** Wire the Notes and Entities views together with a tab switcher in the main dashboard.

**Files:**
- Modify `frontend/src/components/insights/InsightsDashboard.tsx`

**Behavior:**
- Two tabs: "Notes" (default) and "Entities"
- Tab switcher uses the same pill-style selector as the Admin page's period picker
- Stat cards are always visible above the tabs (they show vault-wide stats regardless of active tab)
- Selected note state lives in `InsightsDashboard` and is shared between Notes list, NoteDetail, and EntityBrowser (for cross-linking)

**State shape:**
```typescript
const [activeTab, setActiveTab] = useState<"notes" | "entities">("notes");
const [selectedNotePath, setSelectedNotePath] = useState<string | null>(null);
const [allMetadata, setAllMetadata] = useState<NoteMetadata[]>([]);
const [loading, setLoading] = useState(true);
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Fetch all metadata upfront | Yes (up to 200 notes) | Vault has ~16 notes currently. Even at 200, the payload is small. Avoids pagination UI complexity. Revisit if vault exceeds 200 notes. |
| Suggestions loaded on-demand | Yes (per note, on click) | Suggestions require a vector similarity search. Loading for all 200 notes upfront would be slow and wasteful. |
| No backend changes | Correct | All 6 API endpoints already exist and return the right data. This is purely frontend. |
| Desktop: side-by-side layout | Yes | Follows the master-detail pattern. Note list + detail panel side-by-side is the standard UX for explorer-style views. |
| Mobile: full-width toggle | Yes | Side-by-side doesn't work on mobile. Simple state-based view switching (list vs. detail) is the lightest approach. |
| Entity deduplication on client | Yes | Entity count is small (dozens to low hundreds). Server-side dedup would require a new endpoint. Not worth it. |
| Reuse StatCard pattern | Yes | Matches the Admin page visual language. Consistent design system. |
| No entity graph visualization | For now | Force-directed graphs look cool but add a JS dependency (d3 or vis.js) and complexity. A simple grouped list delivers 90% of the value. Revisit after launch. |

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| Wiki link map visualization | Requires Phase 9 (link-aware retrieval) to be complete first. Add as a follow-up enhancement once link data is available. |
| Note editing / write-back | Phase 12. The Insights page is read-only. |
| Entity graph visualization (force-directed) | Adds a heavy dependency (d3/vis.js). The grouped list is sufficient. Revisit later. |
| Search/filter within the note list | Over-engineering for ~16-50 notes. Add when the vault exceeds 100 notes. |
| Trigger extraction from the UI | The `POST /extract` endpoint exists but triggering it from the UI risks running a long LLM operation during a browser session. Keep it as `make extract` or daily sync. |
| Backlink display | Requires a backlink index that doesn't exist yet. Phase 9's link parser is one-directional (outgoing links only). Backlinks need a separate pass. |

## Implementation Order

```
WI1: API layer (types + fetch functions)
 │
 ├── WI2: Vault overview + note list (depends on WI1 for data)
 │    │
 │    └── WI3: Note detail panel (depends on WI2 for selected state)
 │
 ├── WI4: Entity browser (depends on WI1 for data)
 │
 └── WI5: Tab switcher + wiring (depends on WI2 + WI4 for components)

WI2 and WI4 can be developed in parallel once WI1 is done.
WI3 depends on WI2. WI5 depends on WI2 + WI4.
```

## Testing

**Automated:**
- No backend tests needed (existing APIs are already tested)
- Consider lightweight component tests if the project uses a frontend test framework (currently none detected)

**Manual QA:**
- Desktop (1200px+):
  - Stat cards show correct counts from the API
  - Note list loads and shows all extracted notes with summaries
  - Clicking a note shows the detail panel alongside the list
  - Detail panel shows all sections (summary, entities, dates, action items, connections)
  - Switching to Entities tab shows grouped entity list
  - Entity type filters work (All, People, Orgs, etc.)
  - Clicking a note name in an entity row switches to Notes tab and selects that note
  - Refresh button reloads data
- Mobile (375px, iPhone via Tailscale):
  - Stat cards stack 2x2
  - Note list is full-width and scrollable
  - Tapping a note shows detail view full-width with back button
  - Entity browser is full-width
  - Tab switcher is usable on small screens
- Empty state:
  - With no extracted metadata, show the empty state message
  - With metadata but no suggestions for a note, show "No suggestions available" in the connections section
- Loading:
  - Skeleton cards show while metadata is loading
  - Spinner shows in connections section while suggestions load for a selected note
- Edge cases:
  - Note with no entities → entities section shows "No entities extracted"
  - Note with no action items → section hidden or shows "None"
  - Entity mentioned in 10+ notes → truncated to 3 with "+ 7 more"

## Files Modified

| File | Action |
|------|--------|
| `frontend/src/lib/api.ts` | Modify — add `listMetadata`, `listEntities`, `listActionItems`; type existing wrappers |
| `frontend/src/lib/types.ts` | Modify — add `EntityWithSource`, `ActionItemWithSource` |
| `frontend/src/app/(dashboard)/insights/page.tsx` | Rewrite — replace placeholder with InsightsDashboard |
| `frontend/src/components/insights/InsightsDashboard.tsx` | Create — main dashboard with stat cards, tabs, state management |
| `frontend/src/components/insights/NoteDetail.tsx` | Create — note metadata + suggestions detail panel |
| `frontend/src/components/insights/EntityBrowser.tsx` | Create — entity list with type filtering and grouping |

## Important Notes

- **No backend changes.** All APIs are built, tested, and live. This is 100% frontend.
- **Follow the AdminDashboard pattern** for data fetching (`useEffect` + `useCallback` + `Promise.all`), stat cards, glass-card styling, and loading states.
- **Use existing types** from `types.ts` — `NoteMetadata`, `NoteSuggestions`, `RelatedNote`, `LinkSuggestion`, `TagSuggestion`, `Entity`, `ActionItem` are all defined.
- **After completion**, rebuild and restart the frontend (prod mode):
  ```bash
  cd /Users/brentrossin/SecondBrain/frontend && npm run build
  launchctl unload ~/Library/LaunchAgents/com.secondbrain.ui.plist
  sleep 2 && kill -9 $(lsof -ti:7860) 2>/dev/null
  launchctl load ~/Library/LaunchAgents/com.secondbrain.ui.plist
  ```
