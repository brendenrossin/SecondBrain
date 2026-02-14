# Coordination Note: Server Performance Hardening + Always-On Reliability

> **For:** The agent implementing "Test Quality & Server Performance" (Work Stream B)
> **From:** PM session diagnosing Tailscale reliability issues
> **Date:** 2026-02-14

## Context

A separate PM analysis identified the **root cause** of the phone/Tailscale reliability issues: the Mac Studio sleeps after 1 minute idle, entering a constant sleep/DarkWake cycle (151 cycles since boot). This suspends all processes and drops Tailscale. A separate implementation prompt covers the fix: `docs/features/PROMPT-always-on-reliability.md`.

## What the Always-On Reliability Prompt Covers (NOT your scope)

These items are being handled by a different implementation pass. **Do not duplicate this work:**

1. **Backend API launchd plist installation** — `com.secondbrain.api.plist` wraps uvicorn with `caffeinate -ims` to prevent Mac sleep. Already updated in repo root.
2. **ConnectionMonitor fix** — changing the frontend heartbeat from `fetch("/")` to `fetch("/api/v1/health")` so it detects backend failures, not just frontend failures.
3. **GZip middleware** — adding `GZipMiddleware` to FastAPI to compress API responses over Tailscale.

## What IS Your Scope (and How It Interacts)

Your Work Stream B items are all complementary and should proceed as planned:

| Your Item | Interaction with Always-On work | Notes |
|-----------|-------------------------------|-------|
| `--workers 2` for uvicorn | **IMPORTANT:** If you add workers, also update `com.secondbrain.api.plist` in the repo root. Add `<string>--workers</string>` and `<string>2</string>` to the `ProgramArguments` array (after `<string>8000</string>`). The plist currently has `caffeinate -ims` as the first two args wrapping the uvicorn command. | The installed plist in `~/Library/LaunchAgents/` will be re-copied from the repo root, so only update the repo root copy. |
| `asyncio.to_thread()` wrapping | No conflict | Proceed as planned |
| LLM API timeouts (60s) | No conflict | Proceed as planned |
| Frontend fetch timeouts (AbortController) | Complementary to ConnectionMonitor fix | The ConnectionMonitor detects "server totally down." Your fetch timeouts handle "server up but request is slow." Both are needed. No conflict. |
| Admin stats query optimization | No conflict | Proceed as planned |
| `--timeout-keep-alive 120` | Add to plist if you add it | Same as workers — if you add uvicorn CLI args, also add them to `com.secondbrain.api.plist` in the repo root. |

## The One Thing to Watch

The `com.secondbrain.api.plist` in the repo root is the source of truth for how the API server starts. Its current `ProgramArguments`:

```xml
<array>
    <string>/usr/bin/caffeinate</string>
    <string>-ims</string>
    <string>/Users/brentrossin/.local/bin/uv</string>
    <string>run</string>
    <string>uvicorn</string>
    <string>secondbrain.main:app</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>8000</string>
</array>
```

If you add any uvicorn CLI flags (workers, timeout-keep-alive, etc.), append them here too. The always-on prompt will copy this plist to `~/Library/LaunchAgents/` when it runs.

## Summary

- Sleep prevention + launchd + gzip + ConnectionMonitor = handled elsewhere
- Your server performance items (workers, async, timeouts, query optimization) = proceed as planned
- Just keep the plist in sync if you add uvicorn CLI args
