# ENGAGE-1 — "Today" Surface + Daily Digest Push

> **Status:** In Progress
> **Estimated effort:** ~1 day (shrunk after codebase validation — see below)
> **Depends on:** DW-1 (morning briefing), task aggregation
> **Priority:** Keystone — shared foundation for the ENGAGE and FEED epics

## Problem

SecondBrain "works well" but usage has dropped off. Root cause is not a missing capability — it's that the tool is **pull-only**: it answers when asked and otherwise sits idle. Tools that earn daily use give the user a proactive push that delivers value without being asked (Readwise daily review, Limitless recap, Mem digest). SecondBrain has no such trigger.

## Codebase validation (brainstorming findings)

Validating the original spec against the code shrank this ticket considerably:

- **The "Today" surface already exists.** The home page (`frontend/src/app/(dashboard)/page.tsx`) renders `MorningBriefing` — greeting, date, task counts, today's view. No new page needed.
- **The shared assembly helper already exists.** `_build_briefing(settings)` in `api/briefing.py:45` is already reusable outside the request path and TTL-cached. The digest endpoint reuses it directly.
- **No generic-block refactor.** `BriefingResponse` is a flat, typed model and `BriefingContent` is bespoke, visually-tuned UI. Future sections (resurfacing, feed) will follow the existing **typed-field + bespoke-renderer** idiom (like `today_events`, `yesterday_context`) — not a premature generic block registry.
- **Mac-local notification is useless here.** The user runs SecondBrain from an **iPhone over Tailscale**; a notification fired on the headless Mac Studio would never be seen. Push must reach the phone, and must stay local-first.

## Solution

Deliver the daily re-engagement trigger in a **fully local-first, phone-native** way: a compact digest endpoint on the backend, fetched by a **scheduled iOS Shortcut over Tailscale** that fires a native iPhone notification. Nothing touches Apple/Google/cloud push infrastructure — it's the phone calling the Mac over Tailscale.

### Approaches considered (push delivery)

| Approach | Local-first? | Chosen? |
|----------|-------------|---------|
| Digest endpoint + iOS Shortcut automation | ✅ Fully — phone→Mac over Tailscale, no cloud | **Yes** |
| Self-hosted ntfy | ✅ Android; iOS relays via APNs | No (more moving parts) |
| Web Push (PWA + VAPID) | ⚠️ Routes wake-up via Apple/Google | No |
| macOS local notification (osascript) | ✅ but never seen (headless server) | No |

### WI1: Digest endpoint

**Goal:** A compact, phone-notification-friendly summary the Shortcut can fetch.

**Behavior:**
- `GET /api/v1/digest` — calls `_build_briefing(settings)` and reduces it to `{title, body, count}`:
  - `title` — e.g. "SecondBrain · Aug 2"
  - `body` — one-line status assembled from existing counts, e.g. "3 overdue · 2 due today · 1 aging follow-up". **No LLM — pure string assembly, free.**
  - `count` — total items worth surfacing (drives the "quiet when empty" behavior)
- **Quiet when empty:** if nothing is worth surfacing, return `count: 0` and an empty/neutral body so the Shortcut can choose to fire nothing. Value-forward framing only — never guilt.
- `async` with `asyncio.to_thread` around the blocking assembly (project standard); 503 if vault unavailable (mirror `get_briefing`).
- Extensible by design: when ENGAGE-2 (resurfacing) and FEED-1 (feed) add typed fields to `BriefingResponse`, the digest builder folds their counts into the same one-liner — the shared push channel.

**Files:**
- `src/secondbrain/api/briefing.py` — add `get_digest` route + a small `_build_digest(BriefingResponse) -> DigestResponse` reducer
- `src/secondbrain/models.py` — add `DigestResponse` model

### WI2: iOS Shortcut setup doc

**Goal:** A one-time, on-device automation recipe.

**Behavior:**
- A short doc (`docs/setup/daily-digest-ios-shortcut.md`) with the recipe: Personal Automation → Time of Day (e.g. 8:00am) → Get Contents of URL (`http://<tailscale-name>:8000/api/v1/digest`) → Get Dictionary Value → If `count > 0` → Show Notification (title/body). Set "Run Immediately" (no confirmation).
- Documents the Tailscale hostname/port and that the phone must be on the tailnet.

**Files:** `docs/setup/daily-digest-ios-shortcut.md` (new).

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| Resurfacing logic (spaced-rep, on-this-day) | ENGAGE-2 |
| RSS / content feed | FEED-1 |
| Related-notes panel | ENGAGE-3 |
| Generic block registry / briefing UI refactor | Bespoke UI is fine; future sections use typed-field idiom |
| Settings-page push toggle | Deferred; Shortcut is enabled/disabled on the phone |
| macOS / server-side notification + launchd plist | Never seen by a phone-first user |
| Streaks / badges / gamification | Single-user tool — self-sabotage |
| LLM-written digest | Not needed for ENGAGE-1; counts suffice. FEED-1 adds the LLM brief |

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Digest fires when nothing's worth it (fatigue) | Medium | `count: 0` + Shortcut `if count > 0` gate; quiet by default |
| Tailscale down → Shortcut fetch fails | Low | Shortcut silently no-ops on fetch failure; not fatal |
| Vault unavailable | Low | 503, mirroring `get_briefing` |
| Endpoint drifts from briefing content | Low | Reducer consumes `BriefingResponse` — single source of truth |

## Testing

**Automated:**
- `_build_digest` produces correct title/body/count for empty / partial / full briefings
- `count == 0` when no overdue/due/aging items
- Endpoint returns 503 when vault unavailable
- Body string formatting (pluralization, separators) across cases

**Manual QA:**
- `curl http://localhost:8000/api/v1/digest` → sensible title/body/count
- Set up the iOS Shortcut → fires a native notification at the scheduled time over Tailscale
- Verify quiet behavior: with an all-clear vault, `count: 0` and Shortcut shows nothing

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Digest endpoint + iOS Shortcut | Only option that's both truly local-first (no cloud push) and reaches the phone the user actually uses |
| Reuse `_build_briefing` | Digest is a projection of the briefing — one source of truth |
| No LLM in the digest | Counts suffice; keeps ENGAGE-1 free. LLM brief is FEED-1 |
| Typed-field extensibility, not block registry | Matches existing idiom; preserves polished UI; avoids premature abstraction |
| Quiet when empty | Batching over blasting; protects against notification fatigue |
| Phone-side scheduling, not server cron | The trigger belongs on the device that shows the notification |
