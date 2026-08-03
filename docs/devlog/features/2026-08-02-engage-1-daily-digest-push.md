# Feature: ENGAGE-1 — Daily Digest Push

**Date:** 2026-08-02
**Branch:** engage-1-today-surface-push (merged to main via PR #12)

## Summary

Keystone of the new **ENGAGE** epic. Adds `GET /api/v1/digest` — a compact projection of the morning briefing (`{title, body, count}`) that a scheduled iOS Shortcut fetches over Tailscale to fire a native iPhone notification. This is the first proactive re-engagement trigger in the system: a reason to open SecondBrain each day, delivered fully local-first.

## Problem / Motivation

The tool "works well" but daily usage had dropped off. The root cause was diagnosed as a **retention gap, not a capability gap**: SecondBrain was **pull-only** — it answered when asked and otherwise sat idle. Product research across comparable tools (Readwise daily review, Limitless recap, Mem digest) converged on the finding that daily-use tools give the user a proactive push or a changing surface worth glancing at. SecondBrain had neither.

## Solution

Deliver the re-engagement trigger without any cloud dependency. A pure reducer projects the existing briefing into a one-line status ("3 overdue · 2 due today · 1 aging follow-up"), exposed at `GET /api/v1/digest`. A one-time iOS Shortcut (time-of-day automation) fetches it over Tailscale and shows a native notification, gated on `count > 0` so it stays quiet on all-clear days. Nothing routes through Apple/Google push infrastructure — it's the phone calling the Mac over the tailnet.

## Files Modified

**Backend:**
- `src/secondbrain/models.py` — `DigestResponse` model
- `src/secondbrain/api/briefing.py` — `_short_date`, `_build_digest` (pure reducer over `BriefingResponse`), `get_digest` route reusing the existing `_build_briefing`

**Tests:**
- `tests/test_digest.py` — reducer branch coverage (empty/partial/full, pluralization, ordering, date formatting)
- `tests/test_digest_api.py` — route happy-path + 503 on missing vault (added during tri-review)

**Docs:**
- `docs/setup/daily-digest-ios-shortcut.md` — one-time phone automation recipe
- `docs/features/engage-today-surface-and-push.md` — ENGAGE-1 spec
- `docs/features/feed-attention-router.md` — FEED-1 spec (sibling epic)
- `docs/ROADMAP.md` / `docs/DELIVERED.md` — ENGAGE + FEED epics; ENGAGE-1 delivered

## Key Decisions & Trade-offs

- **Dropped the Mac-local notification.** The original spec proposed an `osascript`/launchd notification on the server. But the user runs SecondBrain from an **iPhone over Tailscale** — a notification on the headless Mac Studio would never be seen. Rethought to a digest endpoint + phone-side scheduling. This surfaced during brainstorming when the user asked "is it even worth having?" — a reminder that push delivery must target the device the user actually looks at.
- **Local-first over convenience.** Considered Web Push (routes through Apple/Google push servers) and self-hosted ntfy (extra service; iOS still relays via APNs). Chose digest + iOS Shortcut because it's the only option that's *both* truly local-first *and* reaches the phone. Trade-off: a one-time manual Shortcut setup on the phone.
- **No generic block registry.** The spec originally proposed refactoring `BriefingResponse` into `blocks: list[BriefingBlock]` with a renderer registry. Codebase validation showed `BriefingContent` is bespoke, visually-tuned UI and each briefing section is already a typed field + bespoke renderer. Chose to keep that idiom for future sections (resurfacing, feed) rather than a premature abstraction — "three similar lines > premature abstraction."
- **Scope shrank after validating the spec against code.** The "Today" surface (home page) and the shared `_build_briefing` helper already existed. ENGAGE-1 collapsed from a 2–3d "surface + push framework" to a ~1d digest endpoint + setup doc. Validating specs against the live codebase before designing paid off directly.
- **No LLM in the digest.** Counts suffice; the body is pure string assembly. Keeps ENGAGE-1 free. The LLM-written brief is deferred to FEED-1.

## Patterns Established

- **Digest = projection of the briefing.** Future ENGAGE/FEED sections that add typed fields to `BriefingResponse` fold their counts into the same one-liner via `_build_digest` — one shared push channel, no Shortcut changes needed.
- **Phone-side scheduling for local-first push.** The scheduling/notification belongs on the device that shows it (iOS Shortcut over Tailscale), not a server cron. This is the template for any future proactive nudge under the local-first constraint.
- **Typed-field + bespoke-renderer** remains the briefing extension idiom; avoid generic block registries on polished surfaces.

## Testing

- Reducer: branch coverage for empty/partial/full briefings, singular vs plural aging, segment ordering, zero-segment skipping, and date formatting (incl. invalid-input pass-through).
- Route: happy-path shape (200, `{title, body, count}`) + 503 on missing/None vault (mirrors `get_briefing`, with cache clear).
- Full suite: 737 passed; ruff + mypy clean. Live-verified against the real vault: `curl /api/v1/digest` → `{"title":"SecondBrain · Aug 2","body":"7 overdue · 8 aging follow-ups","count":15}`.

## Future Considerations

- **ENGAGE-2 (resurfacing)** and **FEED-1 (content feed)** add typed fields to `BriefingResponse`; their counts should fold into `_build_digest`'s one-liner automatically.
- The digest currently reflects only task state (overdue/due/aging). Once resurfacing/feed land, revisit the ordering/priority of segments so the most valuable signal leads.
- iOS Shortcut setup is manual and undocumented beyond the setup file; if more users clone the repo, consider an Android/Tasker equivalent and a troubleshooting section.
- No auth on the endpoint — acceptable under the current model (Tailscale + `127.0.0.1` bind, counts only), consistent with the rest of the API.
