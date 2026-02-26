# Error: False "Server Restarting" Overlay on Mobile/Tailscale

**Date:** 2026-02-14
**Severity:** High
**Component:** Frontend ConnectionMonitor + Backend health endpoint routing

## Symptoms

When using SecondBrain on a phone over Tailscale, the "Server restarting... Will reconnect automatically" overlay would appear after ~30 seconds of normal use and spin indefinitely. Swiping out of the app and returning would temporarily fix it, but it would recur within 30 seconds. The Mac Studio was clearly awake (active SSH session), so sleep/DarkWake was not the cause.

## Root Cause

Two issues combined to create the problem:

1. **Wrong health check URL (primary):** The `ConnectionMonitor` polled `/api/v1/health`, which Next.js proxied to `http://127.0.0.1:8000/api/v1/health`. But the backend only had a health endpoint at `/health` — there was no `/api/v1/health` route. Every health check returned **404**. The monitor happened to work because `fetch()` succeeded (got an HTTP response), and the 404 response was enough to not throw. But `res.ok` returned `false` for 404, so the monitor was always one network hiccup away from triggering.

2. **No fetch timeout (amplifier):** The health check used raw `fetch()` with no `AbortController` timeout. Over Tailscale, if the connection stalled, the fetch would hang for the browser's default timeout (~2-5 minutes), during which the overlay just spun.

3. **Single-failure trigger (amplifier):** A single failed heartbeat immediately showed the overlay. Over Tailscale, transient network blips are common and don't indicate a real outage.

4. **Blocking backend endpoints (secondary):** Several endpoints (`/capture`, `/index`, `/extract`) ran blocking I/O directly in async handlers without `asyncio.to_thread()`, starving the event loop. If any of these were in-flight, the health endpoint couldn't respond, causing legitimate timeouts.

## Fix Applied

1. **Added `/api/v1/health` route alias** on the backend (second `@app.get` decorator on the existing health function) so the frontend proxy path resolves correctly.

2. **Added 5-second AbortController timeout** on the health check fetch in `ConnectionMonitor`, so it fails fast instead of hanging for minutes.

3. **Required 2 consecutive heartbeat failures** before showing the disconnect overlay (`FAILURES_BEFORE_DISCONNECT = 2`), tolerating transient Tailscale blips.

4. **Wrapped blocking endpoints in `asyncio.to_thread()`**: `/capture` (retriever.retrieve), `/index` (entire indexing pipeline extracted to `_run_indexing()`), `/extract` (single-note and batch extraction). This prevents event loop starvation.

5. **Fixed health endpoint status priority**: Low disk warning no longer overwrites a vault error status.

## Files Modified

- `src/secondbrain/main.py` — Added `/api/v1/health` route alias, fixed status priority
- `frontend/src/components/ConnectionMonitor.tsx` — Added timeout, consecutive failure threshold, removed dead code
- `src/secondbrain/api/capture.py` — Wrapped `retriever.retrieve()` in `asyncio.to_thread()`
- `src/secondbrain/api/index.py` — Extracted `_run_indexing()`, wrapped in `asyncio.to_thread()`
- `src/secondbrain/api/metadata.py` — Wrapped `extractor.extract()` and batch loop in `asyncio.to_thread()`
- `tests/test_operational_hardening.py` — Added test for `/api/v1/health` alias, improved test isolation

## How to Prevent

- **Test proxy paths end-to-end.** When a frontend calls `/api/v1/foo` through a Next.js rewrite, verify the backend actually has that route. A 404 that "works" is a latent bug.
- **Always add timeouts to health check fetches.** Health checks are the canary — if they hang, the whole monitoring system is blind.
- **Require multiple failures before alerting.** Single-check thresholds are too sensitive for networks with any variability (Tailscale, mobile, WiFi).
- **Wrap all blocking I/O in `asyncio.to_thread()` in async handlers.** This is now the established pattern for all FastAPI endpoints in this project.

## Lessons Learned

- A 404 that doesn't crash is worse than a 500 that does — it hides the problem. The health monitor appeared to work locally because the fetch "succeeded" (got a response), masking the fact that it was checking the wrong URL.
- The logs told the whole story — dozens of `GET /api/v1/health HTTP/1.1" 404` entries from both Tailscale and localhost. Should have checked logs first.
- Over-eager disconnect overlays create a worse user experience than a brief unresponsive moment. Tolerance for transient failures is essential for mobile/remote access.

## Detection

Discovered by the user seeing the "Server restarting..." overlay repeatedly on their phone over Tailscale. Diagnosed by checking backend logs (`data/api.log`) which showed a flood of 404s to `/api/v1/health`, and verifying that `curl http://localhost:8000/api/v1/health` returned 404 while `curl http://localhost:8000/health` returned 200.
