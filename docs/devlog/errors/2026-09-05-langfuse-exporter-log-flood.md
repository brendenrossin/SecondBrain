# Error: Langfuse OTLP exporter flooded every log with ConnectionError

**Date:** 2026-09-05
**Severity:** Medium
**Component:** `src/secondbrain/tracing.py`, `etc/langfuse/` (Docker stack + launchd job)

## Symptoms

Every `daily_sync` run ended in a wall of stack traces:

```
requests.exceptions.ConnectionError: HTTPConnectionPool(host='localhost', port=3000):
Max retries exceeded with url: /api/public/otel/v1/traces
(Caused by NewConnectionError(... [Errno 61] Connection refused))
```

Repeated several times per run, drowning the actual sync output. The noise
persisted for weeks and was written off as cosmetic. Separately,
`launchctl list | grep langfuse` showed the service stuck at exit status **1**,
and nothing was listening on `localhost:3000`.

## Root Cause

Two independent failures that presented as one.

**1. The log flood — a threading/lifecycle mismatch, not a missing collector.**

`init_tracing` attaches a Langfuse OTLP exporter when keys are configured, and
already wrapped that in a `try/except`:

```python
try:
    processor = _create_langfuse_otlp_processor(...)
    provider.add_span_processor(processor)
except Exception:
    logger.exception("Failed to initialize Langfuse exporter — continuing with JSONL only")
```

That handler can never fire for this failure. `BatchSpanProcessor` only
*constructs* the exporter at init; it **exports from its own background
thread** at flush time. A transport error therefore surfaces long after
`init_tracing` has returned, on a different thread, logged by
`opentelemetry.sdk._shared_internal` — outside any `try` in our code.

Measured with a minimal repro (`init_tracing` + one span + `shutdown()`):
**one span produced 10 lines of stack trace.**

The guard was aimed at the wrong lifecycle stage. Wrapping construction says
nothing about export.

**2. Why the collector was down — a file that was never in git.**

`data/langfuse.log` records the sequence exactly:

```
Container langfuse-langfuse-web-1  Healthy      <- worked
...
Cannot connect to the Docker daemon                <- Docker Desktop stopped
...
no configuration file provided: not found          <- x5
```

`etc/langfuse/docker-compose.yml` had been deleted, and `git ls-files etc/`
showed it was **never tracked** — only `etc/newsyslog.d/` was. So there was
nothing to restore from history, and `docker compose up --wait` failed at every
boot. The `.env` beside it (gitignored, correctly) survived, so no credentials
were lost.

## Fix Applied

**Probe before attaching.** `_langfuse_reachable(host)` does one bounded HTTP
request. Unreachable means the exporter is never attached, so no background
thread exists to fail:

```python
if not _langfuse_reachable(settings.langfuse_host):
    logger.info("Langfuse not reachable at %s — tracing to JSONL only", settings.langfuse_host)
    return
```

Three deliberate choices:

- **Any HTTP status counts as reachable, including 401/404.** The check is for a
  live listener, not a working route. Only a transport failure means "down".
- **`logger.info`, not `warning`.** Langfuse is a *viewer* over spans already
  written to JSONL. Its Docker stack being off loses nothing and requires no
  action — warning-level would train the reader to ignore warnings.
- **`except Exception: return False`.** A probe must never raise into startup.

This does not eliminate the failure mode if Langfuse dies *mid-process* — a
long-lived API server would still log one batch's worth. It removes it entirely
for short-lived processes (`daily_sync`, scripts), which is where the flood was.

**Restored the compose file** from upstream `langfuse v3.225.7` (images identical
to the containers already running) and **committed it**, so it cannot vanish
again.

**Hardened two ports.** Upstream binds `langfuse-web` (3000) and `minio` (9090)
to `0.0.0.0`. This host runs Tailscale, so that would publish the trace UI and
the object store to the entire tailnet. Both now bind `127.0.0.1`, matching the
running containers and the project's default-local rule. The previous (lost)
compose file had clearly done the same — the running containers were already
localhost-bound.

## Files Modified

- `src/secondbrain/tracing.py` — `_langfuse_reachable` + the early return
- `tests/test_tracing.py` — 6 tests (`TestLangfuseReachability`)
- `etc/langfuse/docker-compose.yml` — restored, port-hardened, now tracked

## How to Prevent

- **Infrastructure files belong in git.** A `docker-compose.yml` that a launchd
  job depends on is source, not scratch. `git ls-files` on a config directory is
  a fast audit: if the service needs it and git doesn't have it, it will be lost.
- **Ask where a failure surfaces before wrapping it.** For anything batched,
  queued, or thread-pooled, a `try/except` at the construction site is
  decoration. Check whether the library exports on a background thread.
- **Vendored compose files need a port-binding review.** Upstream defaults to
  `0.0.0.0` because it assumes a private network. On a Tailscale host that is a
  publish-to-the-tailnet decision made silently by a `curl`.
- **Optional dependencies get a preflight, not a retry loop.** Anything the app
  can run without should be probed once and skipped, not retried noisily.

## Lessons Learned

- **Persistent log noise is a bug report you are ignoring.** This ran for weeks
  and was repeatedly dismissed as cosmetic while it buried real sync output. The
  cost was not the disk space; it was that nobody could read the logs.
- **The existing `try/except` created false confidence.** The code *looked*
  defended. Reading it, the reasonable conclusion was "Langfuse failures are
  handled" — which is why the flood was never traced to this function.
- **Reproduce before fixing, and count.** The first two attempts to reproduce
  showed **zero** spam, because the feed's interval guard skipped the run and no
  spans were generated. Stopping there would have "confirmed" the wrong fix. A
  10-line minimal repro (init + one span + flush) gave an exact number to verify
  against: 10 → 0.
- **A dead service can hide behind a live-looking one.** The traces the Admin
  dashboard shows come from `usage.db`, not Langfuse. Trace visibility looked
  fine throughout, which is part of why the collector staying down went unnoticed.

## Detection

Found by reading `daily_sync` output during unrelated FEED-1 work — the flood was
impossible to miss once the feed logs were being read closely.

Earlier detection would have come from:

- **Treating a non-zero launchd exit as an alert.** `launchctl list` showed `1`
  for weeks. A periodic check across `com.secondbrain.*` services would surface
  this in seconds.
- **A startup log line for optional integrations.** The new `INFO` line states
  which sink is active on every run; a JSONL-only run is now self-announcing
  rather than silently degraded.
- **Watching for repeated identical exceptions.** A log line appearing hundreds
  of times per day is a signal regardless of its level.

## Verification

- Minimal repro: **10 spam lines → 0**
- Real `daily_sync feed`: **0** `ConnectionError` lines
- 678 historical Langfuse traces survived the container recreate; a live span
  raised it to **679**
- `localhost:3000` → HTTP 200; `100.96.235.19:3000` (Tailscale) → refused
- launchd service exits **0** (was 1)
- 734 tests pass on this branch (728 + 6 new)
