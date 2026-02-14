# Implementation Prompt: Always-On Reliability

> **Context:** SecondBrain runs on a Mac Studio that acts as a headless server, accessed remotely via Tailscale from an iPhone. Two issues are causing intermittent "server not responding" and perceived slowness on the phone:
>
> 1. The backend API (port 8000) has no launchd service — it dies silently and nothing restarts it
> 2. The Mac Studio is configured to sleep after 1 minute of idle (`sleep = 1`), which suspends all processes and drops the Tailscale tunnel. System logs show 151 sleep/wake cycles since boot — the Mac enters a constant sleep/DarkWake/sleep loop every 45 seconds to 5 minutes. DarkWake only handles TCPKeepAlive maintenance, NOT user process serving.
>
> The frontend (port 7860) already runs via launchd and auto-restarts. The backend needs the same treatment, and the Mac needs to stay awake.
>
> **Approach for sleep prevention:** We use `caffeinate -ims` wrapping the API process in launchd, NOT `pmset -a sleep 0`. This ties wakefulness to the API service itself — no global system changes, no sudo required. When launchd keeps the API alive (KeepAlive=true), caffeinate keeps the Mac awake. If the service is ever unloaded, the Mac is free to sleep again.

Read the feature spec at `docs/features/operational-hardening.md` for background. The API plist already exists at `com.secondbrain.api.plist` in the repo root — it was created but never installed. **It has been updated to wrap the uvicorn command with `caffeinate -ims`.**

---

## Work Item 1: Install Backend API Launchd Service

**Goal:** The backend API auto-starts on boot and auto-restarts on crash.

**Steps:**

1. Kill the current manually-started API server:
   ```bash
   kill -9 $(lsof -ti:8000) 2>/dev/null
   ```

2. Copy the plist from the repo root to LaunchAgents:
   ```bash
   cp /Users/brentrossin/SecondBrain/com.secondbrain.api.plist ~/Library/LaunchAgents/
   ```

3. Load the service:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.secondbrain.api.plist
   ```

4. Wait 5 seconds, then verify:
   ```bash
   sleep 5 && curl -s http://localhost:8000/health
   ```
   Expected: `{"status":"ok","vault":"ok",...}`

5. Verify launchctl shows it:
   ```bash
   launchctl list | grep secondbrain
   ```
   Expected: both `com.secondbrain.ui` and `com.secondbrain.api` should appear.

**IMPORTANT:** The server MUST start from `/Users/brentrossin/SecondBrain/` (the `WorkingDirectory` in the plist handles this). See `docs/devlog/errors/2026-02-13-server-cwd-env-file-silent-failure.md` for why.

---

## Work Item 2: Verify Sleep Prevention via caffeinate

**Goal:** Confirm that the `caffeinate -ims` wrapper in the API plist is keeping the Mac awake.

**Why caffeinate instead of pmset:**
- `pmset -a sleep 0` is a global system change requiring sudo — overkill for this use case
- `caffeinate -ims` is scoped to the API process: `-i` prevents idle sleep, `-m` prevents disk sleep, `-s` prevents system sleep (on AC power)
- When launchd runs the API, caffeinate wraps it. If the API plist is ever unloaded, the Mac is free to sleep normally again
- No sudo required, no global settings changed

**Steps:**

1. After installing the plist (Work Item 1), verify caffeinate is running:
   ```bash
   ps aux | grep caffeinate
   ```
   Expected: a `caffeinate -ims` process wrapping the uvicorn command.

2. Check that sleep assertions are active:
   ```bash
   pmset -g assertions | grep -A2 caffeinate
   ```
   Expected: caffeinate should hold `PreventUserIdleSystemSleep` and `PreventSystemSleep` assertions.

3. Verify the Mac stays awake after 5+ minutes idle:
   ```bash
   pmset -g | grep sleep
   ```
   Note: `sleep = 1` will still show in pmset settings (we didn't change it), but the caffeinate assertion overrides it.

---

## Work Item 3: Fix ConnectionMonitor to Detect Backend Failures

**Goal:** The auto-reconnect overlay detects when the backend API is down, not just the frontend.

**File:** `frontend/src/components/ConnectionMonitor.tsx`

**Current behavior:** The heartbeat does `fetch("/", { method: "HEAD" })` which hits the Next.js frontend server. When the backend dies but the frontend stays up, the overlay never triggers — the user just sees broken/empty data.

**New behavior:** Change the health check to hit `/api/v1/health` instead of `/`. This routes through the Next.js proxy to the backend. If the backend is down, the proxy will return a 502/504, which correctly triggers the reconnect overlay.

**Changes:**

```typescript
// Before
const res = await fetch("/", { method: "HEAD", cache: "no-store" });
return res.ok;

// After
const res = await fetch("/api/v1/health", { cache: "no-store" });
return res.ok;
```

Change from `HEAD` to `GET` since the health endpoint returns JSON (Next.js proxy may not handle HEAD properly for API routes).

Also update the overlay text to be more specific:
- When the backend health check fails: show "Reconnecting to server..." (current text is fine)
- No other changes to the retry logic — 30s heartbeat + 3s retry polling is appropriate

**After modifying frontend files**, rebuild and restart:
```bash
cd /Users/brentrossin/SecondBrain/frontend && npm run build
launchctl unload ~/Library/LaunchAgents/com.secondbrain.ui.plist
sleep 2 && kill -9 $(lsof -ti:7860) 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.secondbrain.ui.plist
sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:7860/
```

---

## Work Item 4: Add GZip Middleware to FastAPI

**Goal:** Compress API JSON responses to reduce transfer size over Tailscale by ~70-80%.

**File:** `src/secondbrain/main.py`

**Changes:** Add one import and one middleware line:

```python
from starlette.middleware.gzip import GZipMiddleware

# Add AFTER the CORSMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500)
```

The `minimum_size=500` means only responses over 500 bytes get compressed. Small responses (health check, root endpoint) are left alone. The big wins are on `/api/v1/briefing`, `/api/v1/tasks`, `/api/v1/insights/*`, and `/api/v1/ask` — all of which return substantial JSON.

**After modifying backend Python files**, restart the API:
```bash
launchctl unload ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 2 && kill -9 $(lsof -ti:8000) 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 3 && curl -s http://localhost:8000/health
```

(By the time you do this work item, the plist should already be installed from Work Item 1.)

---

## Implementation Order

1. **Work Item 1** (install API plist with caffeinate) — do this first, it both manages the API AND prevents sleep
2. **Work Item 2** (verify sleep prevention) — confirm caffeinate is working
3. **Work Item 3** (ConnectionMonitor fix) — frontend change, rebuild required
4. **Work Item 4** (gzip middleware) — backend change, API restart required

Work Items 3 and 4 can be done in either order. After both are done, restart both services.

---

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| `pmset -a sleep 0` (global sleep disable) | Uses caffeinate scoped to API process instead — no global changes, no sudo |
| Bundle size reduction / code splitting | Separate optimization task; not causing the primary reliability issue |
| Tailscale Wake-on-LAN | Unnecessary — caffeinate keeps Mac awake while API runs |
| Backend process monitoring / alerting | Nice to have later, but launchd KeepAlive handles restart |
| HTTPS/TLS on localhost | Tailscale already handles encryption end-to-end |
| uvicorn multi-worker / async wrapping / LLM timeouts | Covered by separate "Server Performance Hardening" work stream (see below) |

---

## Testing

**Automated:** No new tests needed — these are infrastructure/config changes.

**Manual QA (from phone over Tailscale):**
1. Verify the dashboard loads and all API data appears
2. Kill the API process manually (`kill -9 $(lsof -ti:8000)`) — verify:
   - The ConnectionMonitor overlay appears within ~30 seconds
   - launchd restarts the API automatically
   - The overlay disappears and the page reloads once the API is back
3. Let the Mac sit idle for 10+ minutes — verify the dashboard is still responsive from the phone
4. Check that large pages (Insights, Tasks, Briefing) load noticeably faster with gzip

---

## Coordination with Server Performance Hardening

A separate agent is working on "Test Quality & Server Performance" which includes Work Stream B: Server Performance Hardening. That work stream covers:
- Adding uvicorn `--workers 2`
- Wrapping blocking ops with `asyncio.to_thread()`
- Adding LLM API timeouts (60s)
- Adding frontend fetch timeouts (AbortController 30s)
- Optimizing admin stats query

**These do NOT conflict with our work items, but be aware:**
- If the other agent adds `--workers 2` to the uvicorn command, the `com.secondbrain.api.plist` in the repo root needs to be updated to include those args too. Currently the plist has: `caffeinate -ims uv run uvicorn secondbrain.main:app --host 127.0.0.1 --port 8000`. If workers are added, append `--workers 2` to the plist's ProgramArguments array.
- The gzip middleware (our Work Item 4) is NOT in the other agent's scope — we own that.
- The ConnectionMonitor fix (our Work Item 3) is NOT in the other agent's scope — we own that.
- The other agent may add frontend fetch timeouts — that's complementary to our ConnectionMonitor fix, not conflicting.

---

## Commit Workflow

After all 4 work items are done:
1. Run `/test-generation` if any testable logic was added
2. Run `code-simplifier` before committing
3. Commit with a message like: "Add always-on reliability — API launchd service with caffeinate, gzip, and connection monitoring fix"
