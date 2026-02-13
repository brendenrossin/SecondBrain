# Feature: Phase 8.7 — Operational Hardening

**Date:** 2026-02-13
**Branch:** main

## Summary

Added 12 reliability, monitoring, and defensive infrastructure improvements across three tiers. This hardens the SecondBrain backend for unattended operation — auto-restart on crash, meaningful health checks, structured logging, file-based locking, WAL tuning, and sync status visibility in the admin UI.

## Problem / Motivation

SecondBrain runs as an always-on local service accessed over Tailscale. Before this phase, there was no auto-restart on crash, the health endpoint returned only `{"status": "ok"}`, logs could grow unbounded, daily sync failures were invisible, and the reindex process had no concurrency protection. These gaps made the system fragile for unattended operation.

## Solution

12 work items organized into three tiers of decreasing urgency:

**Tier 1 — Critical reliability:**
- Launchd plist (`com.secondbrain.api.plist`) for backend auto-restart with `KeepAlive` and `WorkingDirectory` set to project root (avoiding the `.env` CWD bug)
- Enriched `/health` endpoint: vault existence check, disk space (`shutil.disk_usage`), sync freshness (`.sync_completed` marker mtime)
- Database indexes on `conversations(updated_at)` and `indexed_files(last_indexed_at)`
- Sync completion/failure markers (`.sync_completed`, `.sync_failed`) written by daily_sync
- Log rotation at 10MB threshold with single `.old` backup

**Tier 2 — Defensive infrastructure:**
- Tightened exception handlers in vector store: `except (ChromaError, RuntimeError)` instead of bare `except Exception`
- File-based reindex lock (`.reindex_lock`) with PID tracking, 10-minute stale timeout, `try/finally` release
- WAL tuning: `wal_autocheckpoint=1000` + `synchronous=NORMAL` across all 5 SQLite stores
- Backup/restore Makefile targets (`make backup`, `make restore`)

**Tier 3 — Observability:**
- CORS middleware restricted to `localhost:7860` / `127.0.0.1:7860`
- Structured JSON logging (`_log_structured()`) for critical sync milestones
- Sync status API endpoint (`GET /api/v1/admin/sync-status`) + frontend admin card with color-coded status dot

**Bonus fixes:**
- Converted deprecated `@app.on_event("startup")` to FastAPI lifespan context manager
- Fixed 500 → 503 for missing vault on task update (Phase 8.6 WI3)

## Files Modified

**Backend core:**
- `src/secondbrain/main.py` — Lifespan handler, CORS middleware, enriched health endpoint
- `src/secondbrain/config.py` — Debug setting added
- `src/secondbrain/api/admin.py` — Sync status endpoint
- `src/secondbrain/api/dependencies.py` — Reindex lock mechanism
- `src/secondbrain/api/tasks.py` — 500 → 503 fix
- `src/secondbrain/api/index.py` — Logging on exception handler
- `src/secondbrain/api/briefing.py` — Exception handler tightening
- `src/secondbrain/api/events.py` — Exception handler tightening

**Stores (WAL tuning):**
- `src/secondbrain/stores/conversation.py` — WAL pragmas + index
- `src/secondbrain/stores/index_tracker.py` — WAL pragmas + index
- `src/secondbrain/stores/lexical.py` — WAL pragmas
- `src/secondbrain/stores/metadata.py` — WAL pragmas
- `src/secondbrain/stores/usage.py` — WAL pragmas
- `src/secondbrain/stores/vector.py` — ChromaError exception tightening

**Scripts:**
- `src/secondbrain/scripts/daily_sync.py` — Log rotation, sync markers, structured logging, tighter exception handlers

**Infrastructure:**
- `com.secondbrain.api.plist` — Backend launchd service definition
- `Makefile` — install/uninstall-api-service, backup, restore targets

**Frontend:**
- `frontend/src/lib/api.ts` — `getSyncStatus()` function
- `frontend/src/components/admin/AdminDashboard.tsx` — Sync status card

**Tests (25 new, 318 total):**
- `tests/test_operational_hardening.py` — Health, log rotation, sync status, reindex lock
- `tests/test_main.py` — Lifespan startup logging
- `tests/test_tasks_api.py` — 503 assertion update
- `tests/test_health.py` — Richer health response
- `tests/conftest.py` — Shared fixtures
- `tests/test_briefing_api.py`, `tests/test_events_api.py` — Refactored

**Docs:**
- `docs/ROADMAP.md` — Phase 8.7 checklist
- `docs/features/operational-hardening.md` — Spec document
- `docs/features/server-hardening.md` — Supporting spec

## Key Decisions & Trade-offs

1. **File-based locking over database locking for reindex** — Simpler, visible via `ls`, and the reindex process is inherently single-threaded. PID tracking + stale timeout (10 min) handles crash recovery without external dependencies.

2. **Single `.old` rotation instead of numbered backups** — Keeps log management trivial. Two files max per log (current + `.old`). For a personal system, this is sufficient; numbered rotation adds complexity for minimal benefit.

3. **`synchronous=NORMAL` instead of `FULL`** — Acceptable risk for a local-first system. WAL mode + `NORMAL` gives durability against application crashes (not OS crashes). The vault is the source of truth, so worst case is a rebuild from vault.

4. **Marker files for sync status instead of database** — The daily sync runs as a separate process (launchd cron). ChromaDB's PersistentClient is single-process only, so inter-process communication via marker files avoids the need for a shared database.

5. **Lifespan over `@app.on_event`** — FastAPI deprecated `on_event` in favor of lifespan context managers. The migration was straightforward since there's only startup logic (no shutdown needed yet), but `yield` makes it easy to add shutdown logic later.

6. **CORS restricted to known origins** — Only `localhost:7860` and `127.0.0.1:7860` are allowed. Tailscale access goes through the frontend, not direct API calls, so no additional origins are needed.

## Patterns Established

- **Sync marker convention:** `.sync_completed` contains ISO timestamp, `.sync_failed` contains `{timestamp}: {error message}`. Freshness determined by file mtime, not content.
- **Lock file convention:** `.reindex_lock` contains PID. Stale after 10 minutes. Always use `try/finally` for release.
- **WAL pragma block:** All SQLite stores should include `PRAGMA wal_autocheckpoint=1000` and `PRAGMA synchronous=NORMAL` in their `_init_db()`.
- **Structured logging:** Use `_log_structured(event, **kwargs)` which writes `json.dumps({"event": ..., ...})` via standard logger. For critical operational events only, not routine logging.
- **Exception tightening:** Replace `except Exception` with specific exception types. For ChromaDB: `except (ChromaError, RuntimeError)`.

## Testing

25 new tests across 4 test classes in `test_operational_hardening.py`:
- `TestHealthEndpoint` (7 tests) — vault ok/none/missing, low disk, sync marker states
- `TestRotateLogs` (7 tests) — skip/rotate thresholds, custom size, mixed files
- `TestSyncStatusEndpoint` (6 tests) — all status combinations
- `TestReindexLock` (5 tests) — no trigger, active lock, stale lock, cleanup

Plus 3 tests in `test_main.py` for lifespan startup logging.

All 318 tests pass. `make check` (lint + typecheck + test) is green.

## Future Considerations

- **Backend launchd service not yet installed** — The plist was created but not loaded via `make install-api-service`. The backend currently runs via manual `nohup`. Install when ready to switch to fully managed operation.
- **Log rotation runs only during daily sync** — If the API server produces large logs between syncs, they won't be rotated until the next sync. Could add a periodic rotation check to the API server itself.
- **No alerting** — Health degradation is visible via `/health` and the admin UI, but there's no push notification when the vault goes missing or disk runs low. Could integrate with macOS notifications or a simple webhook.
- **Backup target is local-only** — `make backup` copies to `backups/`. For true disaster recovery, these should be copied off-machine (e.g., to iCloud or a remote).
