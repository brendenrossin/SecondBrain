# Calendar Week Grid — Multi-Column Desktop + Day-Picker Mobile

> **Status:** Planned (Phase 8.5)
> **Estimated effort:** 3-5 days
> **Depends on:** Phase 7.5 (calendar events), Phase 8 (task management UI)

## Problem

The calendar page renders as a **vertical scrollable list** of day sections. On desktop, you must scroll through 5-7 cards to see the whole week — no at-a-glance view. On mobile, there's no day-level navigation; you scroll the same list on a smaller screen with no way to quickly jump to a specific day or see which days are busy.

Additionally, the Tasks page truncates task titles on mobile to just a few characters ("S...", "Cr...", "Begin w...") due to the `truncate` CSS class combined with excessive padding and fixed-width right-side controls. The calendar view's compact task cards need to handle this properly from the start.

## Solution

Two responsive layouts for the calendar page:

1. **Desktop (`md+`):** Replace the vertical list with a multi-column grid — one column per day, all visible at once. A 5-day/7-day toggle with smart defaults (5 on weekdays, 7 on weekends).

2. **Mobile (`< md`):** A day-picker ribbon showing all 7 days with badge summaries (event count, task count with urgency colors). Tapping a day shows that day's full details below. Today is selected by default.

---

### Work Item 1: Fix Mobile Task Text Truncation

**Goal:** Task titles and event titles wrap instead of truncating on narrow screens, across the Tasks page, Home page (morning briefing), and calendar components.

**Current problem:**
- `TaskItem.tsx` line 92: `truncate` class forces single-line ellipsis
- Combined with `px-5 mx-2` padding on the item + `px-8` on the page + `shrink-0` on right-side controls → text gets ~200px on a 375px screen
- Result: "Setup AI Receptionist..." becomes "S..."
- `MorningBriefing.tsx` line 41: `BriefingTaskItem` has `truncate` on task text — overdue/due-today tasks on the home page truncate to "Set up Arize AX con...", "Create a ticket for t..."
- `MorningBriefing.tsx` line 252: Event title in "Today's View" card has `truncate` — events truncate to "Pick up Gone Bananas cinnam..."

**Changes:**
- **`frontend/src/components/tasks/TaskItem.tsx`:**
  - Remove `truncate` from the task text `<p>` element
  - Replace with responsive behavior: `break-words` to allow wrapping on mobile
  - Reduce horizontal padding on mobile: `px-3 md:px-5` on the task row, `mx-1 md:mx-2` on outer wrapper
  - The right-side controls (status icon, due badge, age label) keep `shrink-0`

- **`frontend/src/app/(dashboard)/tasks/page.tsx`:**
  - Reduce page padding on mobile: `px-4 md:px-8`

- **`frontend/src/components/briefing/MorningBriefing.tsx`:**
  - Line 41 (`BriefingTaskItem`): Remove `truncate` from the task text element, replace with `break-words`
  - Line 252 (event title in "Today's View"): Remove `truncate`, replace with `break-words`
  - Reduce horizontal padding on the briefing content area on mobile: `px-4 md:px-8`

**Testing:** Visual QA on 375px viewport — task titles and event titles should wrap, not truncate to fragments. Check Tasks page, Home page overdue section, Home page Today's View card.

---

### Work Item 2: Desktop Multi-Column Grid Component

**Goal:** On `md+` breakpoints, render the week as a horizontal grid of equal-width columns.

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  < Feb 10 – 14, 2026 >  [Today]  [5d ○ 7d]             │
├─────────────────────────────────────────────────────────┤
│  ┌─ Multi-day event banner (spans columns) ───────────┐ │
│  └────────────────────────────────────────────────────┘ │
├───────────┬───────────┬───────────┬───────────┬─────────┤
│  MON 10   │  TUE 11   │  WED 12   │  THU 13   │ FRI 14  │
│  ● today  │           │           │           │         │
│───────────│───────────│───────────│───────────│─────────│
│  Event    │           │  Event    │           │ Event   │
│  10:30 AM │           │  9:00 AM  │           │ 12:00   │
│───────────│───────────│───────────│───────────│─────────│
│  ☐ Task 1 │  ☐ Task 3 │  ☐ Task 5 │           │ ☐ Task 6│
│  ☐ Task 2 │           │           │           │         │
├───────────┴───────────┴───────────┴───────────┴─────────┤
│  Overdue (2)                                            │
│  ☐ Task from Feb 8    ☐ Task from Feb 7                 │
├─────────────────────────────────────────────────────────┤
│  No Due Date (3)                                        │
│  ☐ Unscheduled task 1   ☐ Unscheduled task 2   ...     │
└─────────────────────────────────────────────────────────┘
```

**Behavior:**
- Columns are equal-width flex children: `flex-1 min-w-0`
- Each column has a sticky header (day name + date + optional "today" indicator)
- Events render above tasks within each column (existing pattern)
- Empty columns show header only — visual rhythm shows free days
- All columns share the same height; each column scrolls independently if content overflows (via `overflow-y-auto` with a `max-h` tied to viewport)
- Overdue section: full-width below the grid, only on current week (existing logic)
- No-due-date section: full-width below overdue (existing logic)

**Column header design:**
- Day abbreviation (Mon, Tue...) in `text-text-dim text-xs uppercase`
- Date number (10, 11...) in `text-text text-lg font-semibold`
- Today: small accent dot or accent-colored date number
- Subtle bottom border separator

**Compact card variants (needed for column width):**
- Event cards: icon + title (truncate with ellipsis) + time badge. No padding bloat.
- Task cards: status icon + title (truncate with ellipsis). Category breadcrumb hidden in grid view — too wide. Due badge shown as small colored dot indicator, not full text.
- Full details available on hover (tooltip) or click (existing task detail panel)

**Files:**
- `frontend/src/components/calendar/WeekGrid.tsx` — new component, the multi-column grid
- `frontend/src/components/calendar/DayColumn.tsx` — new component, single column
- `frontend/src/components/calendar/CompactTask.tsx` — new component, slim task card for columns
- `frontend/src/components/calendar/CompactEvent.tsx` — new component, slim event card for columns
- `frontend/src/components/calendar/WeeklyAgenda.tsx` — conditional render: `WeekGrid` on `md+`, mobile view on `< md`

---

### Work Item 3: 5-Day / 7-Day Toggle

**Goal:** A toggle in the week navigation bar to switch between weekday-only (5) and full-week (7) column views.

**Behavior:**
- Toggle renders as a small segmented control: `5d` / `7d` next to the Today button
- **Smart default:** If today is Saturday or Sunday, default to 7d. Otherwise default to 5d.
- Default resets on each page visit (no persistence). User may request localStorage persistence later.
- In 5d mode: show Monday–Friday. Week navigation advances by 7 days (still a full week), but only 5 columns render.
- In 7d mode: show Monday–Sunday. All 7 columns render.
- The date range label in WeekNav updates accordingly: "Feb 10 – 14" (5d) vs "Feb 10 – 16" (7d)
- Mobile view always shows 7 days in the ribbon (toggle is desktop-only, hidden below `md`)

**Files:**
- `frontend/src/components/calendar/WeekNav.tsx` — add toggle control, update date range label
- `frontend/src/components/calendar/WeeklyAgenda.tsx` — manage `showWeekend` state, pass to WeekGrid

---

### Work Item 4: Mobile Day-Picker Ribbon

**Goal:** On mobile (`< md`), replace the scrollable day list with a day-picker ribbon + single-day detail view.

**Layout:**
```
┌─────────────────────────────┐
│  < Feb 9 – 15 >    [Today] │
├─────────────────────────────┤
│ ┌───┐┌───┐┌─────┐┌───┐┌───┐┌───┐┌───┐
│ │Mon││Tue││ Wed ││Thu││Fri││Sat││Sun│
│ │ 9 ││10 ││ 11  ││12 ││13 ││14 ││15 │
│ │   ││🟢2││     ││🟢1││   ││   ││   │
│ │⚠1 ││☑3 ││     ││☑2 ││   ││   ││   │
│ └───┘└───┘└─────┘└───┘└───┘└───┘└───┘
│              ▲ selected
│
│  ── Wednesday, Feb 11 ─────────
│
│  EVENTS
│  🟢 Team standup  9:00 AM
│
│  TASKS
│  ☐ Submit tax docs
│
│  OVERDUE (if viewing today)
│  ⚠ Fix login bug (due Feb 8)
│
└─────────────────────────────┘
```

**Day button behavior:**
- 7 equal-width buttons in a horizontal row (always 7, no 5d/7d toggle on mobile)
- Each button shows:
  - Day abbreviation (Mon, Tue...) — `text-[10px] text-text-dim`
  - Date number — `text-sm font-medium`
  - Badge row (below date):
    - Event count: small calendar icon + number in emerald (`text-emerald-400`)
    - Task count: small check icon + number, colored by urgency:
      - Red/rose if any overdue tasks on that day
      - Amber if tasks due today
      - Neutral (`text-text-dim`) for future tasks
    - Badges only shown if count > 0
- **Selected state:** Accent border (bottom or full border), slightly elevated background (`bg-white/[0.04]`). Remove the badge icons/counts from the selected button (since the detail view below shows full info).
- **Today indicator:** Small accent dot above the day abbreviation (visible in both selected and unselected states)

**Detail view below ribbon:**
- Shows the selected day's events and tasks using the existing `DaySection`-style rendering (full-width cards, not compact)
- Events above tasks (existing pattern)
- Overdue section shown only when viewing the current day (today) — consistent with current behavior
- Task titles wrap (WI1 fix), not truncate

**Default selection:** Today. If navigating to a different week, select Monday.

**Files:**
- `frontend/src/components/calendar/DayRibbon.tsx` — new component, the 7-button day picker
- `frontend/src/components/calendar/DayButton.tsx` — new component, individual day button with badges
- `frontend/src/components/calendar/MobileDayView.tsx` — new component, detail view for selected day
- `frontend/src/components/calendar/WeeklyAgenda.tsx` — conditional render based on breakpoint

---

### Work Item 5: Responsive Breakpoint Orchestration

**Goal:** Wire up the responsive switching between desktop grid and mobile day-picker.

**Approach:**
- Use a `useMediaQuery` hook (or Tailwind's `md` breakpoint via CSS) to detect viewport
- `WeeklyAgenda.tsx` becomes the orchestrator:
  - `>= md (768px)`: render `WeekNav` + `MultiDayBanner` + `WeekGrid` + `OverdueSection` + no-due-date section
  - `< md`: render `WeekNav` (without 5d/7d toggle) + `DayRibbon` + `MobileDayView`
- Both layouts share the same data fetching (tasks + events for the week range)
- Both layouts share the same week navigation state (`weekOffset`)
- Multi-day event banners: shown above the grid on desktop. On mobile, multi-day events appear as regular event cards on each day they span.

**Files:**
- `frontend/src/components/calendar/WeeklyAgenda.tsx` — refactor as orchestrator
- `frontend/src/hooks/useMediaQuery.ts` — new hook (if not already present)

---

## Implementation Order

```
Work Item 1: Fix mobile task text truncation (prerequisite, standalone)
    │
Work Item 2: Desktop multi-column grid (core feature)
    ├── Work Item 3: 5d/7d toggle (depends on grid existing)
    │
Work Item 4: Mobile day-picker ribbon (independent of desktop grid)
    │
Work Item 5: Responsive orchestration (depends on WI2 + WI4)
```

WI1 can ship independently. WI2 and WI4 can be developed in parallel. WI3 and WI5 are finishing touches.

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| **Swipe gestures on mobile** | Tap-only for v1. Swiping between days conflicts with horizontal scroll and adds complexity. Revisit if users request it. |
| **Hourly time grid** | This is a week agenda, not Google Calendar. No need for hour-by-hour slots. Events show their time as a badge. |
| **Drag-and-drop task rescheduling** | Would be nice but significant complexity. Vault is source of truth — would need write-back. |
| **localStorage persistence for 5d/7d** | Smart default resets each visit. User may request persistence later. |
| **Month view** | Week-based view is the right granularity for daily planning. Month view is a separate feature. |
| **Task detail panel in grid view** | Clicking a task in the grid could open the detail panel (Phase 8), but the compact cards themselves don't need inline editing. Existing panel behavior should work if already wired up. |

## Testing

**Automated:**
- `useMediaQuery` hook: test that it returns correct values for different viewport widths
- Day badge calculations: test event/task count aggregation and urgency color logic
- 5d/7d toggle: test that column count changes, date range label updates

**Manual QA:**
- Desktop 1200px+: verify 5-column grid with all days visible, no horizontal scroll
- Desktop 768-1200px: verify grid still works with narrower columns
- Desktop 7d mode: verify all 7 columns render, toggle switches correctly
- Mobile 375px: verify day ribbon fits 7 buttons, badges are readable
- Mobile: tap each day button, verify detail view updates
- Mobile: verify selected button loses badges, others keep them
- Mobile: verify overdue section only appears when viewing today
- Tasks page: verify task titles wrap on mobile (WI1)
- Calendar compact cards: verify task titles truncate with ellipsis (acceptable in narrow columns)
- Week navigation: verify both desktop and mobile advance/retreat by full weeks

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Equal-height columns with independent scroll** | Prevents layout jag from one busy day pushing all columns down. Clean grid appearance. |
| **Overdue section below grid, not in columns** | Overdue tasks are a "fix this" pile, not day-specific. Putting them in past-day columns would be confusing (is it overdue because it's in Monday's column, or because it's past due?). |
| **No category breadcrumb in compact cards** | Horizontal space is precious in columns. Category is nice-to-have context, not essential for scanning. Available via click/hover. |
| **7 days always in mobile ribbon** | Consistent with the week range shown in navigation. A 5-day ribbon on weekdays would hide weekend data. |
| **Smart default 5d/7d without persistence** | Avoids complexity. The default covers the common case (weekdays during the week, all days on weekends). Manual toggle for edge cases. |
| **Wrap task text on mobile (Tasks page), truncate in compact grid cards** | Different contexts need different solutions. The Tasks page has full width — wrapping is correct. Grid columns are 180px — truncation with tooltip/click is correct. |
| **Multi-day events as regular cards on mobile** | Spanning banners don't work in single-day view. Showing the event on each day it spans is clear and simple. |

---

## Known Minor Issues

_To be populated during implementation review._

| Issue | Severity | Notes |
|-------|----------|-------|

---

**Implementation order — follow this sequence:**

#### Step 1: Fix mobile text truncation across Tasks page and Home page (WI1)

1. **`frontend/src/components/tasks/TaskItem.tsx`:**
   - Line ~92: Remove the `truncate` class from the task text `<p>` element
   - Replace with `break-words` (or `overflow-wrap: anywhere`) so text wraps on narrow screens
   - Line ~71: Change padding from `px-5` to `px-3 md:px-5` and margin from `mx-2` to `mx-1 md:mx-2`
   - Keep the right-side controls' `shrink-0`

2. **`frontend/src/app/(dashboard)/tasks/page.tsx`:**
   - Find the container with `px-8` padding and change to `px-4 md:px-8`

3. **`frontend/src/components/briefing/MorningBriefing.tsx`:**
   - Line ~41: In `BriefingTaskItem`, remove `truncate` from the task text element, replace with `break-words`
   - Line ~252: In the "Today's View" card, remove `truncate` from the event title `<span>`, replace with `break-words`
   - Find the content area container with `px-8` padding and change to `px-4 md:px-8` (applies to the scrollable content div)

4. **Verify:** Check at 375px viewport width:
   - Tasks page: titles should wrap, not show "S..."
   - Home page overdue section: titles should wrap, not show "Set up Arize AX con..."
   - Home page Today's View: event titles should wrap, not show "Pick up Gone Bananas cinnam..."

#### Step 2: Build compact card variants (part of WI2)

1. **Create `frontend/src/components/calendar/CompactTask.tsx`:**
   - Slim task card for grid columns (~180px wide)
   - Status icon (circle/dot/check — clickable, same toggle logic as `AgendaTask`)
   - Task title with `truncate` (ellipsis is correct here — columns are narrow)
   - Small colored dot for due date urgency (red=overdue, amber=today, blue=upcoming, none=no date)
   - No category breadcrumb, no full due badge text
   - Text size: `text-xs` (12px)
   - On click: open task detail panel if it exists, or do nothing for now

2. **Create `frontend/src/components/calendar/CompactEvent.tsx`:**
   - Slim event card for grid columns
   - Small calendar icon (emerald) + title with `truncate`
   - Time badge if present (compact: "10:30a" not "10:30 AM")
   - Text size: `text-xs`

#### Step 3: Build the desktop grid (WI2)

1. **Create `frontend/src/components/calendar/DayColumn.tsx`:**
   - Props: `date: Date, events: CalendarEvent[], tasks: Task[], isToday: boolean`
   - Header: day abbreviation (`text-text-dim text-[10px] uppercase tracking-wide`), date number (`text-lg font-semibold`), today indicator (accent dot or accent-colored number)
   - Body: CompactEvent cards, then CompactTask cards
   - Style: `flex-1 min-w-0 flex flex-col` with `overflow-y-auto` body area
   - Border between columns: `border-r border-border` (except last)
   - Subtle hover highlight on the column header area

2. **Create `frontend/src/components/calendar/WeekGrid.tsx`:**
   - Props: `weekStart: Date, tasks: Task[], events: CalendarEvent[], showWeekend: boolean`
   - Renders 5 or 7 `DayColumn` components in a flex row
   - Groups tasks by due date, events by date
   - Days with no content still render (empty column body)
   - Set a max height on the grid area: `max-h-[calc(100vh-280px)]` (adjust as needed so overdue/no-date sections are visible below)

3. **Style the grid container:**
   - `flex flex-row` for columns
   - `rounded-2xl border border-border bg-surface-1` (glass-card style, consistent with existing design)
   - No horizontal scroll — columns flex to fill

#### Step 4: Add 5d/7d toggle (WI3)

1. **`frontend/src/components/calendar/WeekNav.tsx`:**
   - Add a segmented control after the Today button: two small buttons `5d` and `7d`
   - Active state: `bg-accent/15 text-accent` — inactive: `text-text-dim`
   - Only visible on `md+` (hide on mobile with `hidden md:flex`)
   - Props: add `showWeekend: boolean, onToggleWeekend: (show: boolean) => void`
   - Update the date range label: if `showWeekend` is false, show "Mon, Feb 10 – Fri, Feb 14"; if true, show "Mon, Feb 10 – Sun, Feb 16"

2. **`frontend/src/components/calendar/WeeklyAgenda.tsx`:**
   - Add state: `const [showWeekend, setShowWeekend] = useState(() => { const day = new Date().getDay(); return day === 0 || day === 6; })`
   - Pass `showWeekend` to `WeekGrid` and `WeekNav`

#### Step 5: Build mobile day-picker (WI4)

1. **Create `frontend/src/components/calendar/DayButton.tsx`:**
   - Props: `date: Date, eventCount: number, taskCount: number, hasOverdue: boolean, hasDueSoon: boolean, isSelected: boolean, isToday: boolean, onClick: () => void`
   - Layout (vertical stack, centered):
     - Today dot: small `w-1.5 h-1.5 rounded-full bg-accent` dot above day name (only if `isToday`)
     - Day abbreviation: `text-[10px] text-text-dim uppercase`
     - Date number: `text-sm font-medium`
     - Badge row (only if NOT selected):
       - Event badge: `CalendarDays` icon (10px) + count in `text-emerald-400` — only if eventCount > 0
       - Task badge: `CheckCircle2` icon (10px) + count — color depends on urgency:
         - `text-rose-400` if `hasOverdue`
         - `text-amber-400` if `hasDueSoon` (due today)
         - `text-text-dim` otherwise
       - Only if taskCount > 0
   - Selected state: `border-b-2 border-accent bg-white/[0.04]`
   - Unselected: `border-b-2 border-transparent`
   - Size: `flex-1` (equal width, 7 buttons fill the row)
   - Min height ~64px to fit badges

2. **Create `frontend/src/components/calendar/DayRibbon.tsx`:**
   - Props: `weekStart: Date, tasks: Task[], events: CalendarEvent[], selectedDate: Date, onSelectDate: (date: Date) => void`
   - Renders 7 `DayButton` components in a `flex flex-row`
   - Calculates per-day counts: events, tasks, overdue status, due-soon status
   - Container: `bg-surface-1 border-b border-border`

3. **Create `frontend/src/components/calendar/MobileDayView.tsx`:**
   - Props: `date: Date, events: CalendarEvent[], tasks: Task[], overdueTasksForToday: Task[]`
   - Header: "Wednesday, Feb 11" in `text-sm font-medium text-text-dim`
   - Events section (if any): renders existing `AgendaEvent` components (full-width, not compact)
   - Tasks section (if any): renders existing `AgendaTask` components (full-width, wrapping text)
   - Overdue section (if viewing today and overdue tasks exist): existing `OverdueSection` component
   - Empty state: "Nothing scheduled" centered text

#### Step 6: Wire up responsive orchestration (WI5)

1. **Create `frontend/src/hooks/useMediaQuery.ts`** (if it doesn't exist):
   - Simple hook: `useMediaQuery(query: string): boolean`
   - Uses `window.matchMedia`, handles SSR (default false), listens for changes

2. **Refactor `frontend/src/components/calendar/WeeklyAgenda.tsx`:**
   - Add `const isDesktop = useMediaQuery('(min-width: 768px)')`
   - Add `const [selectedDate, setSelectedDate] = useState(new Date())`
   - Keep existing data fetching (tasks + events for the week range)
   - Render logic:
     ```
     if (isDesktop) {
       <WeekNav ... showWeekend toggle .../>
       <MultiDayBanner .../>
       <WeekGrid .../>
       <OverdueSection .../>
       {no-due-date section}
     } else {
       <WeekNav ... (no toggle) .../>
       <DayRibbon ... selectedDate onSelectDate .../>
       <MobileDayView ... selectedDate .../>
     }
     ```
   - When week changes, reset `selectedDate` to Monday of new week (or today if current week)
   - Multi-day events on mobile: filter events for the selected day, including multi-day events that span that day (reuse existing overlap logic from `WeeklyAgenda`)

**Important implementation notes:**

- **Use existing design patterns.** Look at `DaySection.tsx`, `AgendaTask.tsx`, `AgendaEvent.tsx` for the established styling (glass-card, emerald accents, text sizes, icon usage). Match them.
- **Don't modify the API.** All data comes from existing `getTasks()` and `getEvents()` calls. No backend changes needed.
- **Preserve existing task interactions.** Status toggle (checkbox click) must work in both compact and full cards. The `onToggleStatus` callback pattern from `AgendaTask` should be reused.
- **The 5d/7d toggle is desktop-only.** Don't render it on mobile. Don't add localStorage. The smart default is: `new Date().getDay() === 0 || new Date().getDay() === 6`.
- **Multi-day event banners stay on desktop.** On mobile, multi-day events render as regular `AgendaEvent` cards on each day they span.
- **Keep the "No Due Date" section on desktop only.** Mobile focuses on the selected day; undated tasks live on the Tasks page.
- **Follow the commit workflow:** write code -> `/test-generation` -> `code-simplifier` -> commit.
- **Read `CLAUDE.md` for build/restart instructions** after frontend changes. The frontend runs in production mode via launchd — you need to `npm run build` and restart the service.
