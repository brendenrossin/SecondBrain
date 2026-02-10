# Calendar Events — Appointments, Visits & Multi-Day Events

> **Status:** Planned (Phase 7.5)
> **Estimated effort:** 3-5 days
> **Depends on:** Phase 5.5 (inbox upgrade — better segmentation + Anthropic models help event classification)

## Problem

The calendar page only shows tasks with due dates. Real life has more than tasks — appointments, visits, trips, events. When the user dictates "my mom is coming at 10:30 tomorrow," the inbox processor classifies it as a generic note and files it in `10_Notes/Mom Visiting Tomorrow.md`. The calendar shows nothing.

**Real examples from the vault today:**

1. `10_Notes/Mom Visiting Tomorrow.md` — "Mom is coming up to drop off a birthday present for Rachel tomorrow (February 10) around 10:30 AM. Consider adding to calendar." Classified as a note. Not on the calendar.

2. `10_Notes/Rachels Birthday Gift Travel Plans.md` — "Rachel's parents get in on the 17th of February and then we go down to San Diego on the 20th." Mixed with unrelated content (Snowflake resume, Noah Kahan tickets). Multi-day visit information buried in prose.

The system has no concept of "event" — only tasks (actionable, completable) and notes (static text).

## Solution

Add **events** as a first-class concept alongside tasks and notes. Events are time-bound occurrences that aren't actionable — you don't "complete" your mom visiting.

### Four work items:

---

### Work Item 1: Inbox Event Classification

**Goal:** The inbox processor recognizes events and extracts structured data.

**Approach:**
- Add `"event"` to the classification prompt's `note_type` enum: `"daily_note" | "note" | "project" | "concept" | "living_document" | "event"`
- Add event fields to the classification JSON output:
  ```json
  {
    "note_type": "event",
    "event_title": "Mom dropping off Rachel's birthday present",
    "event_date": "2026-02-10",
    "event_time": "10:30",
    "event_end_date": null,
    "suggested_title": "Mom Visiting",
    ...
  }
  ```
- Add classification guidance:
  - `"event"`: A specific occurrence at a date/time — appointments, visits, trips, arrivals/departures. NOT a task (nothing to "do"), NOT a general note.
  - If an event spans multiple days, set `event_end_date` (e.g., "Rachel's parents visiting Feb 17–24")
  - Time is optional — "Rachel's parents arrive the 17th" has a date but no time; "Mom at 10:30" has both

**Key distinction in the prompt:**
- "Follow up with Snowflake recruiter" → **task** (actionable)
- "Mom coming at 10:30 tomorrow" → **event** (time-bound occurrence)
- "Rachel's parents arriving the 17th through the 24th" → **event** with end_date

**File:** `src/secondbrain/scripts/inbox_processor.py`

---

### Work Item 2: Event Storage in Daily Notes

**Goal:** Events are stored in daily notes under a `## Events` section, keeping the vault as source of truth.

**Vault format:**
```markdown
## Events
- 10:30 — Mom dropping off Rachel's birthday present
- Rachel's parents visiting (through Feb 24)
```

**Format rules:**
- One event per bullet
- Timed events: `- HH:MM — description`
- All-day events: `- description`
- Multi-day events: `- description (through YYYY-MM-DD)` or `- description (Feb 17–24)`
- End date stored in parentheses at end — human-readable, machine-parseable

**Routing logic:**
- `note_type == "event"` → route to `00_Daily/{event_date}.md` under `## Events` section
- If the daily note doesn't exist, create it (same as task routing)
- If `## Events` section doesn't exist, add it after `## Focus` / before `## Notes`
- Append event as a bullet item
- Duplicate detection: skip if same event text already exists in that day's events

**File:** `src/secondbrain/scripts/inbox_processor.py`

---

### Work Item 3: Event Parser + API

**Goal:** Read events from daily notes and serve via API.

**Event data model:**
```python
@dataclass
class Event:
    title: str           # "Mom dropping off Rachel's birthday present"
    date: str            # "2026-02-10" (YYYY-MM-DD)
    time: str            # "10:30" or "" if all-day
    end_date: str        # "2026-02-24" or "" if single-day
    source_file: str     # "00_Daily/2026-02-10.md"
```

**Parser:**
- Scan daily notes for `## Events` sections (same pattern as task parsing in `task_aggregator.py`)
- Parse each bullet:
  - `- HH:MM — text` → timed event
  - `- text (through YYYY-MM-DD)` → multi-day event
  - `- text` → all-day event
- Return list of `Event` objects

**API endpoint:**
```
GET /api/v1/events?start=YYYY-MM-DD&end=YYYY-MM-DD
```
Returns events within the date range. Multi-day events included if any part overlaps the range.

**Response:**
```json
[
  {
    "title": "Mom dropping off Rachel's birthday present",
    "date": "2026-02-10",
    "time": "10:30",
    "end_date": "",
    "source_file": "00_Daily/2026-02-10.md"
  },
  {
    "title": "Rachel's parents visiting",
    "date": "2026-02-17",
    "time": "",
    "end_date": "2026-02-24",
    "source_file": "00_Daily/2026-02-17.md"
  }
]
```

**Files:**
- `src/secondbrain/scripts/event_parser.py` — new file, event parsing logic
- `src/secondbrain/api/events.py` — new file, API endpoint
- `src/secondbrain/main.py` — register events router

---

### Work Item 4: Frontend Calendar Events

**Goal:** Show events on the calendar alongside tasks.

**Single-day / timed events:**
- Rendered as a card in the DaySection, visually distinct from tasks
- Different icon (calendar icon instead of circle bullet)
- Time shown prominently if present: `10:30 AM` badge on the left
- Different accent color or subtle background to distinguish from tasks
- Events appear ABOVE tasks in a day section (appointments are time-sensitive)

**Multi-day events:**
- Shown as a subtle banner/bar at the top of the week view
- Spans across the relevant days
- Label: "Rachel's parents visiting" with date range
- Doesn't take up the full day height — a thin, colored bar
- If a multi-day event extends beyond the visible week, show with an arrow/indicator

**Frontend types:**
```typescript
interface CalendarEvent {
  title: string;
  date: string;       // YYYY-MM-DD
  time: string;       // "10:30" or ""
  end_date: string;   // "2026-02-24" or ""
  source_file: string;
}
```

**Data fetching:**
- `getEvents(start, end)` API call in `api.ts`
- WeeklyAgenda fetches events for the current week range alongside tasks
- Events and tasks rendered together in DaySection

**Files:**
- `frontend/src/lib/types.ts` — CalendarEvent type
- `frontend/src/lib/api.ts` — getEvents function
- `frontend/src/components/calendar/WeeklyAgenda.tsx` — fetch + pass events
- `frontend/src/components/calendar/DaySection.tsx` — render events above tasks
- `frontend/src/components/calendar/AgendaEvent.tsx` — new component for event cards
- `frontend/src/components/calendar/MultiDayBanner.tsx` — new component for spanning events

---

## Implementation Order

```
Work Item 1: Inbox classification (event type + fields)
    └─ Work Item 2: Daily note routing (## Events section)
Work Item 3: Event parser + API (can start in parallel with 1-2)
    └─ Work Item 4: Frontend (depends on API)
```

Items 1-2 are inbox pipeline changes. Items 3-4 are read-path changes. They can be developed somewhat in parallel.

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| **Extracting events from existing notes** | The "Rachel's parents" note in `10_Notes/` has events buried in mixed-topic prose. Retroactive extraction from all notes is a different problem. For v1, events enter through the inbox and live in daily notes. Users can manually add events to daily note `## Events` sections. |
| **Recurring events** | "Every Tuesday standup" requires a recurrence engine. Out of scope for v1. |
| **Calendar integrations (Google Calendar, iCal)** | Read-only calendar integration is a future exploration (see `docs/features/EXPLORATION-calendar-integration.md`). |
| **Event editing in the UI** | Vault is source of truth. Edit events in Obsidian. |
| **Time zones** | Single user, single location. All times are local. |
| **Reminders / notifications** | Separate feature, not part of calendar display. |

## Testing

**Automated:**
- Event parser: test bullet parsing for timed, all-day, and multi-day formats
- Inbox classification: test that event-like dictation produces `note_type: "event"` (mocked LLM)
- Event routing: test that events are appended to daily note `## Events` section
- API: test date range filtering, multi-day overlap logic

**Manual QA:**
- Dictate "Mom visiting at 10:30 tomorrow" → verify it appears on calendar
- Dictate "Rachel's parents here Feb 17 through 24" → verify multi-day banner
- Navigate weeks → verify events appear in correct days
- Mix of events and tasks on same day → verify events render above tasks

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Events in daily notes, not separate files** | Consistent with tasks. Daily note is "what's happening on this day." Keeps parsing simple — same scan pattern as tasks. |
| **`## Events` section format** | Human-readable in Obsidian. Machine-parseable with simple regex. Users can manually add events directly. |
| **No checkboxes on events** | Events aren't completable. Your mom visiting isn't a todo. |
| **Events above tasks in day view** | Appointments are time-sensitive context. Knowing "mom at 10:30" before seeing your task list helps you plan the day. |
| **Multi-day as banner, not repeated** | A week-long visit shouldn't appear 7 times as individual cards. A spanning banner is the right metaphor. |
