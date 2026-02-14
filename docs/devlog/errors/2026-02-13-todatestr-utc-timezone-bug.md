# Error: toDateStr() Uses UTC Instead of Local Timezone

**Date:** 2026-02-13
**Severity:** Critical
**Component:** Frontend — `lib/utils.ts`, affects calendar, tasks, briefing, and all date comparisons

## Symptoms

- Calendar page defaults to Saturday instead of Friday (the actual local day)
- "Due Today" task counts are wrong after 4 PM PST (midnight UTC)
- Overdue task detection off by one day in the evening
- Week grid highlights the wrong day as "today"
- Mobile day ribbon selects the wrong day on load

## Root Cause

The `toDateStr()` utility function used `date.toISOString().split("T")[0]` to produce a `YYYY-MM-DD` string. `toISOString()` converts to **UTC**, so any time after 4 PM PST (midnight UTC), `new Date()` becomes tomorrow's date string.

```typescript
// BROKEN — converts to UTC
export function toDateStr(date: Date): string {
  return date.toISOString().split("T")[0];
}
```

This single function is called by every component that compares dates as strings: `WeeklyAgenda`, `WeekGrid`, `DayRibbon`, `MobileDayView`, `TaskTree`, and more. All of them derive `todayStr = toDateStr(new Date())`, so the off-by-one error cascaded everywhere.

Every other date function in the codebase (`formatDate`, `daysUntil`, `startOfWeek`, `addDays`, `toLocaleDateString`) already used local-timezone Date methods. Only `toDateStr` broke the contract by silently converting to UTC.

## Fix Applied

Replaced `toISOString()` with explicit local-timezone extraction:

```typescript
export function toDateStr(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
```

This uses `getFullYear()`, `getMonth()`, `getDate()` which all return values in the browser's local timezone — consistent with every other date utility in the codebase.

No other files needed changes because all other date handling already used local-timezone methods. The `AdminDashboard.toDateKey()` helper was already implemented correctly with the same local-timezone approach.

## Files Modified

- `frontend/src/lib/utils.ts` — Fixed `toDateStr()` (the only change needed)

## How to Prevent

1. **Never use `toISOString()` for local date strings.** It converts to UTC which causes off-by-one errors in any timezone west of UTC (most of the Americas).
2. **Use `getFullYear()`/`getMonth()`/`getDate()`** for local date string formatting.
3. **Add a lint rule or code comment** warning against `toISOString()` in date-to-string conversions.
4. **Test date logic at 11 PM local time** — this is when UTC-vs-local bugs become visible (the date flips to tomorrow in UTC while it's still today locally).

## Lessons Learned

- `toISOString()` is one of the most common sources of timezone bugs in JavaScript. It looks correct in testing during daytime hours because UTC and local time share the same date for most of the day. The bug only manifests in the evening (for US timezones).
- A single utility function used by 10+ components means a single timezone bug cascades everywhere. The fix is also single-point, which is the upside of centralizing date logic.
- The `new Date(dateStr + "T00:00:00")` pattern used elsewhere in the codebase (for parsing date strings back into Date objects at local midnight) is correct and consistent — it was only the reverse direction (`Date → string`) that was broken.

## Detection

User noticed the calendar was defaulting to Saturday instead of Friday (PST). The symptom is only visible when the user is in a timezone behind UTC and checks the app after their local time crosses midnight UTC (4 PM PST / 5 PM PDT).

Earlier detection options:
- Unit test that creates a date at 11 PM local time and verifies `toDateStr()` returns today's date, not tomorrow's
- E2E test that mocks `Date.now()` to evening hours and checks calendar highlights the correct day
