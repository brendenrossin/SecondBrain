# Implementation Agent Prompt: Insights Dashboard

You are implementing the Insights Dashboard for the SecondBrain project. Read the full feature spec first:

- `docs/features/insights-dashboard.md`

**This is 100% frontend work. Do NOT create or modify any backend Python files.** All API endpoints already exist and are tested.

---

## Context

- The Insights page at `frontend/src/app/(dashboard)/insights/page.tsx` is currently a "Coming soon" placeholder
- The backend has 6 API endpoints ready (built in Phase 3, months ago):
  - `GET /api/v1/metadata` — all note metadata, paginated
  - `GET /api/v1/metadata/{path}` — single note metadata
  - `GET /api/v1/suggestions/{path}` — related notes, link suggestions, tag suggestions
  - `GET /api/v1/entities?entity_type=` — all entities across vault
  - `GET /api/v1/action-items` — all action items
  - `POST /api/v1/extract` — trigger extraction (do NOT use from frontend)
- Frontend types for metadata and suggestions already exist in `frontend/src/lib/types.ts`
- Two API wrappers already exist in `frontend/src/lib/api.ts`: `getMetadata(path)` and `getSuggestions(path)` — but they return `Record<string, unknown>` instead of typed responses

## Reference pattern

**Copy the `AdminDashboard` architecture exactly.** Read these files as your template:

- `frontend/src/app/(dashboard)/admin/page.tsx` — page wrapper pattern (header bar + scrollable content)
- `frontend/src/components/admin/AdminDashboard.tsx` — stat cards, data fetching with `useEffect`/`useCallback`/`Promise.all`, glass-card styling, loading states, period selector pattern

Also look at these for UI component patterns:
- `frontend/src/components/layout/Sidebar.tsx` — the Insights nav item is already wired (purple theme)
- `frontend/src/lib/utils.ts` — the `cn()` utility for conditional classNames

---

## Step-by-step implementation

### Step 1: API layer (`frontend/src/lib/api.ts` + `frontend/src/lib/types.ts`)

**In `types.ts`**, add:
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

**In `api.ts`**, add three new functions:
```typescript
export async function listMetadata(offset = 0, limit = 200): Promise<NoteMetadata[]> {
  return fetchJSON(`${BASE}/metadata?offset=${offset}&limit=${limit}`);
}

export async function listEntities(entityType?: string): Promise<{ entities: EntityWithSource[]; total: number }> {
  const qs = entityType ? `?entity_type=${entityType}` : "";
  return fetchJSON(`${BASE}/entities${qs}`);
}

export async function listActionItems(): Promise<{ action_items: ActionItemWithSource[]; total: number }> {
  return fetchJSON(`${BASE}/action-items`);
}
```

**Also fix the existing wrappers** to return typed responses:
```typescript
export async function getMetadata(path: string): Promise<NoteMetadata> {
  return fetchJSON(`${BASE}/metadata/${encodeURIComponent(path)}`);
}

export async function getSuggestions(path: string): Promise<NoteSuggestions> {
  return fetchJSON(`${BASE}/suggestions/${encodeURIComponent(path)}`);
}
```

Add the necessary imports from `types.ts` for `NoteMetadata`, `NoteSuggestions`, `EntityWithSource`, `ActionItemWithSource`.

### Step 2: InsightsDashboard component (`frontend/src/components/insights/InsightsDashboard.tsx`)

Create the main dashboard component. It manages:
- `allMetadata: NoteMetadata[]` — fetched on mount via `listMetadata()`
- `entityData` — fetched on mount via `listEntities()`
- `actionItemData` — fetched on mount via `listActionItems()`
- `activeTab: "notes" | "entities"` — tab state
- `selectedNotePath: string | null` — which note is selected for detail view
- `loading: boolean`

**On mount**, fetch all three in parallel with `Promise.all` (same pattern as AdminDashboard).

**Layout:**
1. Stat cards row (4 cards, `grid grid-cols-2 lg:grid-cols-4 gap-4`):
   - Notes Extracted (count of metadata entries)
   - Total Entities (from entity data)
   - Key Phrases (count unique across all metadata)
   - Action Items (total, subtitle shows high priority count)
2. Tab switcher (pill-style, same as Admin period selector)
3. Active tab content: either Notes view (list + detail) or Entity browser

Use the `StatCard` pattern from AdminDashboard — define it inline or extract a shared component. Use the same icon imports from `lucide-react` (e.g., `FileText`, `Users`, `Tag`, `Zap`).

### Step 3: Notes list + detail panel

**Inside `InsightsDashboard.tsx` or as child components:**

**Note list:**
- Map over `allMetadata`, sorted alphabetically by note title (extract from note_path filename)
- Each row: note title, folder badge (first path segment), summary truncated to 2 lines, entity count, action item count
- Clicking a row sets `selectedNotePath`
- Selected row has `bg-accent/10 border-accent/30` highlight

**Desktop layout (≥768px):** side-by-side with `md:grid md:grid-cols-[2fr_3fr] md:gap-6`
**Mobile (<768px):** when no note selected, show list full-width. When note selected, show detail full-width with a back button.

### Step 4: NoteDetail component (`frontend/src/components/insights/NoteDetail.tsx`)

Props: `notePath: string`, receives the selected note path.

**Data:**
- The metadata is passed as a prop (already in parent state) or looked up from the parent's `allMetadata` array
- Suggestions are fetched on-demand: `getSuggestions(notePath)` when the component mounts or `notePath` changes
- Show a loading spinner in the "Connections" section while suggestions load

**Sections (all in a single scrollable column):**
1. **Header** — title (bold, large), full path (dim, small), extracted date + model
2. **Summary** — the summary text in a glass-card
3. **Key Phrases** — pill badges: `px-2 py-0.5 rounded-full text-xs bg-accent/10 text-accent`
4. **Entities** — grouped by type, each with emoji prefix and confidence
5. **Dates** — each with type badge and normalized date
6. **Action Items** — priority-coded list
7. **Related Notes** (from suggestions) — title, similarity score, shared entities
8. **Suggested Links** (from suggestions) — target title, anchor text, confidence
9. **Suggested Tags** (from suggestions) — tag name, confidence

Use `glass-card` for each section grouping. Sections with no data should show a subtle "None" or be hidden entirely.

### Step 5: EntityBrowser component (`frontend/src/components/insights/EntityBrowser.tsx`)

Props: `entities: EntityWithSource[]`, `onSelectNote: (path: string) => void`

**Behavior:**
- Type filter tabs at top: All | People | Orgs | Products | Places (pill-style selector)
- Client-side grouping: deduplicate by `(text, entity_type)` → collect unique note_paths per entity
- Each entity row: entity text (bold), list of note titles (comma-separated, max 3 shown + "and N more")
- Clicking a note title calls `onSelectNote(path)` which switches to Notes tab and selects that note

### Step 6: Page wrapper (`frontend/src/app/(dashboard)/insights/page.tsx`)

Replace the placeholder. Follow the Admin page pattern exactly:

```tsx
"use client";

import { Lightbulb } from "lucide-react";
import { InsightsDashboard } from "@/components/insights/InsightsDashboard";

export default function InsightsPage() {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2.5 px-6 h-14 border-b border-border shrink-0">
        <Lightbulb className="w-4.5 h-4.5 text-text-dim" />
        <h1 className="text-base font-bold text-text tracking-tight">Insights</h1>
      </div>
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <InsightsDashboard />
      </div>
    </div>
  );
}
```

---

## What NOT to do

- Do NOT create or modify any backend Python files — all APIs already exist
- Do NOT add a `POST /extract` trigger button in the UI
- Do NOT add a graph/network visualization (no d3, vis.js, etc.)
- Do NOT add search/filter to the note list (premature for ~16 notes)
- Do NOT add routing — use component state for selected note and tab switching, not Next.js routes
- Do NOT add new colors or design tokens — use existing ones from the Tailwind config

## Commit workflow

After implementing:
1. Write the code
2. Run `code-simplifier` agent to review before committing
3. Commit with a descriptive message

## After implementation

Rebuild and restart the frontend:
```bash
cd /Users/brentrossin/SecondBrain/frontend && npm run build
launchctl unload ~/Library/LaunchAgents/com.secondbrain.ui.plist
sleep 2 && kill -9 $(lsof -ti:7860) 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.secondbrain.ui.plist
sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:7860/
```
