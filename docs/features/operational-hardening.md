# Operational Hardening — Reliability, Monitoring, and Defensive Infrastructure

> **Status:** Planned (Phase 8.7)
> **Estimated effort:** 2-3 days
> **Depends on:** Phase 8.6 (server hardening — absolute paths and 503 errors)

## Problem

SecondBrain is functionally stable but operationally fragile. Failures are silent, logs grow unbounded, the backend has no auto-restart, health checks are trivial, and there's no backup strategy. As the vault grows and the system runs for months, these gaps compound.

**Recent incident:** The server started from the wrong directory and all APIs silently returned empty — no error logged, no alert, no indication that anything was wrong. This is a symptom of a broader pattern: the system assumes everything is fine and has no defensive mechanisms when it isn't.

## Solution

12 work items across three tiers of priority, all shipping as Phase 8.7.

---

### Tier 1: High Impact, Low Effort

---

### Work Item 1: Backend API Launchd Service

**Goal:** The backend auto-starts on boot and auto-restarts on crash, with correct working directory guaranteed.

**Create:** `~/Library/LaunchAgents/com.secondbrain.api.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.secondbrain.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/brentrossin/.local/bin/uv</string>
        <string>run</string>
        <string>uvicorn</string>
        <string>secondbrain.main:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8000</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/brentrossin/SecondBrain</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>/Users/brentrossin/SecondBrain/data/api.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/brentrossin/SecondBrain/data/api.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/Users/brentrossin/.local/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

**After creating:**
```bash
cp com.secondbrain.api.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 3 && curl -s http://localhost:8000/health
```

**Update MEMORY.md and CLAUDE.md** to reflect the new restart procedure:
```bash
# Restart backend:
launchctl unload ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 2 && kill -9 $(lsof -ti:8000) 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 3 && curl -s http://localhost:8000/health
```

---

### Work Item 2: Meaningful Health Endpoint

**Goal:** `/health` verifies the system is actually functional, not just alive.

**File:** `src/secondbrain/main.py` (lines 62-65)

**Replace the current trivial health check with:**
```python
@app.get("/health")
async def health() -> dict[str, Any]:
    import shutil
    from secondbrain.config import get_settings
    s = get_settings()

    checks: dict[str, Any] = {"status": "ok"}

    # Vault check
    if not s.vault_path or not s.vault_path.exists():
        checks["status"] = "error"
        checks["vault"] = "not configured or missing"
    else:
        checks["vault"] = "ok"

    # Disk space
    _, _, free = shutil.disk_usage(str(s.data_path))
    free_gb = round(free / (1024**3), 2)
    checks["free_disk_gb"] = free_gb
    if free_gb < 1.0:
        checks["status"] = "warning"
        checks["disk"] = "low"

    # Sync freshness
    sync_marker = s.data_path / ".sync_completed"
    if sync_marker.exists():
        import time
        age_hours = (time.time() - sync_marker.stat().st_mtime) / 3600
        checks["last_sync_hours_ago"] = round(age_hours, 1)
        if age_hours > 25:
            checks["sync"] = "stale"
    else:
        checks["last_sync_hours_ago"] = None

    return checks
```

**Testing:** `curl http://localhost:8000/health` should return vault status, disk space, and sync age.

---

### Work Item 3: Missing Database Indexes

**Goal:** Add indexes on columns used in WHERE/ORDER BY clauses to prevent query degradation as data grows.

**File: `src/secondbrain/stores/conversation.py`** — in `_init_schema()`:
```sql
CREATE INDEX IF NOT EXISTS idx_conversations_updated
    ON conversations(updated_at DESC);
```
This speeds up `list_conversations()` (line ~279) which orders by `updated_at DESC`.

**File: `src/secondbrain/stores/index_tracker.py`** — in `_init_schema()`:
```sql
CREATE INDEX IF NOT EXISTS idx_indexed_files_last_indexed
    ON indexed_files(last_indexed_at);
```
This speeds up `get_stats()` (line ~153) which queries `MAX(last_indexed_at)`.

**Note:** `lexical.py` and `metadata.py` already have appropriate indexes. Only conversation and index_tracker need additions.

---

### Work Item 4: Daily Sync Completion Marker

**Goal:** The system can tell whether the last sync succeeded and when.

**File:** `src/secondbrain/scripts/daily_sync.py`

**At the end of the `main()` function (after all sync steps complete successfully):**
```python
from pathlib import Path
from datetime import datetime
marker = Path(settings.data_path) / ".sync_completed"
marker.write_text(datetime.now().isoformat())
logger.info("Sync completed successfully at %s", datetime.now().isoformat())
```

**On failure (in the outer exception handler if one exists, or add one):**
```python
marker = Path(settings.data_path) / ".sync_failed"
marker.write_text(f"{datetime.now().isoformat()}: {str(e)}")
logger.error("Sync FAILED: %s", e)
```

**Integration:** The health endpoint (WI2) reads `.sync_completed` mtime. Future UI work can surface "Last sync: 2h ago" on the admin page.

---

### Work Item 5: Log Rotation

**Goal:** Log files don't grow unbounded.

**Create:** `~/Library/LaunchAgents/com.secondbrain.log-rotation.plist` (or a simple script run weekly)

**Simpler approach — add a Makefile target and call it from daily sync:**

**File: `src/secondbrain/scripts/daily_sync.py`** — add at the start of `main()`:
```python
def _rotate_logs(data_path: Path, max_size_mb: float = 10.0) -> None:
    """Rotate log files that exceed max_size_mb."""
    for log_name in ["daily-sync.log", "api.log", "ui.log"]:
        log_file = data_path / log_name
        if log_file.exists() and log_file.stat().st_size > max_size_mb * 1024 * 1024:
            rotated = data_path / f"{log_name}.old"
            if rotated.exists():
                rotated.unlink()
            log_file.rename(rotated)
            logger.info("Rotated %s (exceeded %.1f MB)", log_name, max_size_mb)
```

Call `_rotate_logs(data_path)` at the start of each daily sync run. Keeps current + one rotated copy. Simple, no external dependencies.

**Also rotate `queries.jsonl`** with the same logic.

---

### Tier 2: Prevents Future Pain

---

### Work Item 6: Tighten Exception Handlers

**Goal:** Catch specific exceptions, not blanket `Exception`, so bugs aren't masked as "database errors."

**File: `src/secondbrain/stores/vector.py`**

8 locations use `except Exception:`. The reconnect-pattern ones (lines 153, 190, 230, 258, 276, 285) should catch a more specific exception. ChromaDB raises various exceptions — use a combined catch:

```python
# At the top of the file:
from chromadb.errors import ChromaError

# Replace each reconnect-pattern handler:
# FROM:
except Exception:
    self._reconnect()
    ...
# TO:
except (ChromaError, RuntimeError):
    self._reconnect()
    ...
```

For the metadata-access handlers (lines 63, 75), these should remain `except Exception` since they're accessing dict metadata that could fail in various ways — but add logging:
```python
except Exception:
    logger.debug("VectorStore: could not read embedding model metadata", exc_info=True)
    return None
```

**File: `src/secondbrain/api/index.py`** (line 105):
```python
# FROM:
except Exception:
    continue
# TO:
except Exception:
    logger.warning("Failed to read note: %s", file_path, exc_info=True)
    continue
```

**File: `src/secondbrain/scripts/daily_sync.py`** (line 44):
```python
# FROM:
except Exception:
    return "Reindex trigger written..."
# TO:
except (urllib.error.URLError, OSError, TimeoutError) as e:
    logger.info("API reindex trigger failed (%s), using file trigger", e)
    return "Reindex trigger written..."
```

**Note:** `lexical.py` already uses specific `sqlite3.DatabaseError` catches everywhere — it's the gold standard. Other stores should follow its pattern.

---

### Work Item 7: Reindex Lock

**Goal:** Prevent double-reindex if daily sync and manual trigger overlap.

**File:** `src/secondbrain/api/dependencies.py` — in `check_and_reindex()` (line ~218)

**Add a lock file mechanism:**
```python
import time

lock_file = data_path / ".reindex_lock"

# Check for existing lock
if lock_file.exists():
    lock_age = time.time() - lock_file.stat().st_mtime
    if lock_age < 600:  # Lock valid for 10 minutes
        logger.info("Reindex already in progress (lock age: %.0fs), skipping", lock_age)
        return None
    else:
        logger.warning("Stale reindex lock (%.0fs old), removing", lock_age)
        lock_file.unlink()

# Acquire lock
lock_file.write_text(str(os.getpid()))
try:
    # ... existing reindex logic ...
finally:
    lock_file.unlink(missing_ok=True)
```

---

### Work Item 8: WAL Checkpoint Tuning

**Goal:** Explicit WAL checkpoint configuration on all SQLite stores.

SQLite's default `wal_autocheckpoint` is 1000 pages (~4MB), which is fine. But being explicit prevents surprises and documents intent.

**Add to all 5 stores** (`conversation.py`, `metadata.py`, `index_tracker.py`, `lexical.py`, `usage.py`) in the connection setup, after the WAL and busy_timeout pragmas:
```python
self._conn.execute("PRAGMA wal_autocheckpoint=1000")
```

Also add `PRAGMA synchronous=NORMAL` which is the recommended setting for WAL mode (faster writes, still crash-safe):
```python
self._conn.execute("PRAGMA synchronous=NORMAL")
```

---

### Work Item 9: Backup Command

**Goal:** One-command backup of all derived data.

**Add to `Makefile`:**
```makefile
backup:
	@mkdir -p ~/SecondBrain-backups
	@BACKUP_DIR=~/SecondBrain-backups/data-$$(date +%Y%m%d-%H%M%S); \
	cp -r data "$$BACKUP_DIR" && \
	echo "Backup complete: $$BACKUP_DIR ($$(du -sh "$$BACKUP_DIR" | cut -f1))"
```

**Add to `Makefile`:**
```makefile
restore:
	@echo "Available backups:"; ls -1d ~/SecondBrain-backups/data-* 2>/dev/null || echo "  No backups found"
	@echo "To restore: cp -r ~/SecondBrain-backups/data-YYYYMMDD-HHMMSS data"
```

---

### Tier 3: Polish

---

### Work Item 10: CORS Middleware

**Goal:** Safety net for future frontend/backend separation.

**File:** `src/secondbrain/main.py`

**Add after app creation:**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:7860", "http://127.0.0.1:7860"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Restrict to localhost origins. No wildcard. This is defensive — the Next.js proxy handles CORS today, but if the proxy config ever changes, the API won't break.

---

### Work Item 11: Structured Logging for Critical Events

**Goal:** Key events logged as parseable JSON for easier debugging.

**File:** `src/secondbrain/scripts/daily_sync.py`

**At the end of each sync step, log a structured summary:**
```python
import json

def _log_structured(event: str, **kwargs: Any) -> None:
    logger.info(json.dumps({"event": event, **kwargs}))

# After inbox processing:
_log_structured("inbox_complete", processed=count, failed=failed_count, duration_ms=elapsed)

# After reindex:
_log_structured("reindex_complete", files=indexed_count, duration_ms=elapsed)

# After metadata extraction:
_log_structured("extraction_complete", extracted=count, failed=failed, duration_ms=elapsed)
```

**Don't convert all logging to JSON** — just the critical sync milestones. Human-readable logs remain for everything else.

---

### Work Item 12: Sync Status in Admin UI

**Goal:** Admin page shows when the last sync ran and whether it succeeded.

**Backend:** Add a new field to the admin stats endpoint (or create a dedicated endpoint):

**File:** `src/secondbrain/api/admin.py` (or wherever admin stats live)
```python
@router.get("/admin/sync-status")
async def sync_status(settings: Annotated[Settings, Depends(get_settings)]) -> dict:
    data_path = Path(settings.data_path)
    result = {"last_sync": None, "status": "unknown"}

    completed = data_path / ".sync_completed"
    failed = data_path / ".sync_failed"

    if completed.exists():
        mtime = completed.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        result["last_sync"] = completed.read_text().strip()
        result["status"] = "stale" if age_hours > 25 else "ok"
        result["hours_ago"] = round(age_hours, 1)

    if failed.exists() and (not completed.exists() or failed.stat().st_mtime > completed.stat().st_mtime):
        result["status"] = "failed"
        result["error"] = failed.read_text().strip()

    return result
```

**Frontend:** Add a small indicator to the Admin page — "Last sync: 2h ago" with green/amber/red status dot.

**File:** `frontend/src/components/admin/AdminDashboard.tsx` — add a sync status card at the top, similar to the existing stat cards.

---

## Implementation Order

```
Tier 1 (do first — highest value):
  WI1: Launchd plist for backend (eliminates cwd bug permanently)
  WI2: Health endpoint (catches misconfigurations)
  WI3: Database indexes (prevents future slowdown)
  WI4: Sync completion marker (foundation for WI2 + WI12)
  WI5: Log rotation (prevents unbounded growth)

Tier 2 (do second):
  WI6: Tighten exception handlers
  WI7: Reindex lock
  WI8: WAL checkpoint tuning
  WI9: Backup command

Tier 3 (do last):
  WI10: CORS middleware
  WI11: Structured logging
  WI12: Sync status in admin UI (depends on WI4)
```

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| **Push notifications / email alerts** | Over-engineering for a single-user app. Log + UI indicators are sufficient. |
| **Automated monthly backups** | `make backup` is sufficient. User can add to cron later if desired. |
| **Full structured logging migration** | Only critical sync events get JSON. Converting all logging is unnecessary churn. |
| **Rate limiting** | Bound to localhost, single user. Tailscale handles network-level access. |
| **Dependency update automation** | Lock files handle reproducibility. Manual updates with `make check` are fine. |
| **Inbox processor idempotency refactor** | Important but large scope — separate feature if pursued. |

## Testing

**Automated:**
- Health endpoint: test with valid vault, missing vault, low disk space (mocked)
- Log rotation: test that files over threshold are renamed
- Reindex lock: test that concurrent reindex attempts are blocked
- Sync marker: test that `.sync_completed` is written on success

**Manual QA:**
- Reboot machine → verify backend auto-starts via launchd
- Kill backend process → verify launchd restarts it within 10 seconds
- Run `make backup` → verify `~/SecondBrain-backups/` contains data copy
- Run `make restore` → see available backups listed
- Check `/health` → verify vault, disk, and sync info returned
- Check admin page → verify sync status indicator (WI12)

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Launchd over systemd/supervisor** | Native macOS. Already used for frontend and daily sync. Consistent. |
| **Simple log rotation over logrotate** | No external dependency. 10MB threshold + 1 rotated copy is sufficient. |
| **Lock file over database lock** | Reindex is a cross-store operation. A file lock is simpler than coordinating across SQLite + ChromaDB. |
| **503 for missing vault (from Phase 8.6)** | Makes the health endpoint's vault check meaningful — if health says "ok", the APIs work. |
| **`PRAGMA synchronous=NORMAL` for WAL** | SQLite docs recommend NORMAL for WAL mode. FULL is overkill for single-user local app. |

## Known Minor Issues

_To be populated during implementation review._

| Issue | Severity | Notes |
|-------|----------|-------|
