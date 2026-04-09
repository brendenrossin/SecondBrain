# Log Persistence & Data Retention — Bounded, Surviving Restarts

> **Status:** Planned (Phase 8.9.1)
> **Estimated effort:** 1 day
> **Depends on:** Phase 6.7 (LLM observability — done)

## Problem

SecondBrain runs as a local service via launchd on a Mac Studio. Two gaps make debugging and monitoring harder than they should be:

1. **Application logs (stdout/stderr) are lost on every restart.** Launchd captures them to temporary buffers but doesn't persist them to disk. If the server crashes at 3am and auto-restarts, the error is gone. The only surviving record is whatever got written to `usage.db` — but application-level warnings, startup diagnostics, and non-LLM errors vanish.

2. **`usage.db` grows unbounded.** Every LLM call adds a row forever. At ~20 calls/day, that's ~7,300 rows/year — manageable now, but there's no mechanism to prune old data. At scale (more features, more LLM calls), the anomaly detection SQL queries will slow down as they scan the full table.

Neither is critical today, but both are the kind of thing that bites you 6 months from now when you're trying to debug a problem that happened last week and the logs are gone.

## Solution

Two independent, lightweight changes:

### Work Item 1: Launchd Log Persistence with Rotation

**Goal:** Application stdout/stderr survives restarts, bounded to prevent disk bloat.

**Approach:** Use launchd's built-in `StandardOutPath` / `StandardErrorPath` plist keys to redirect output to log files, then use macOS's native `newsyslog` to rotate them.

**Changes:**

1. Update `com.secondbrain.api.plist`:
   ```xml
   <key>StandardOutPath</key>
   <string>/Users/brentrossin/SecondBrain/data/logs/api.stdout.log</string>
   <key>StandardErrorPath</key>
   <string>/Users/brentrossin/SecondBrain/data/logs/api.stderr.log</string>
   ```

2. Update `com.secondbrain.ui.plist`:
   ```xml
   <key>StandardOutPath</key>
   <string>/Users/brentrossin/SecondBrain/data/logs/ui.stdout.log</string>
   <key>StandardErrorPath</key>
   <string>/Users/brentrossin/SecondBrain/data/logs/ui.stderr.log</string>
   ```

3. Update `com.secondbrain.daily-sync.plist`:
   ```xml
   <key>StandardOutPath</key>
   <string>/Users/brentrossin/SecondBrain/data/logs/daily-sync.stdout.log</string>
   <key>StandardErrorPath</key>
   <string>/Users/brentrossin/SecondBrain/data/logs/daily-sync.stderr.log</string>
   ```

4. Add a `newsyslog` configuration at `/etc/newsyslog.d/secondbrain.conf`:
   ```
   # logfilename                                          [owner:group]  mode  count  size  when  flags
   /Users/brentrossin/SecondBrain/data/logs/api.stdout.log               644   3      5120  *     N
   /Users/brentrossin/SecondBrain/data/logs/api.stderr.log               644   3      1024  *     N
   /Users/brentrossin/SecondBrain/data/logs/ui.stdout.log                644   3      1024  *     N
   /Users/brentrossin/SecondBrain/data/logs/ui.stderr.log                644   3      1024  *     N
   /Users/brentrossin/SecondBrain/data/logs/daily-sync.stdout.log        644   3      1024  *     N
   /Users/brentrossin/SecondBrain/data/logs/daily-sync.stderr.log        644   3      1024  *     N
   ```
   This keeps 3 rotated copies, rotates at 5MB for the API log and 1MB for the others.

5. Create `data/logs/` directory (add to `.gitignore`).

**Files:**
- `~/Library/LaunchAgents/com.secondbrain.api.plist`
- `~/Library/LaunchAgents/com.secondbrain.ui.plist`
- `~/Library/LaunchAgents/com.secondbrain.daily-sync.plist`
- `/etc/newsyslog.d/secondbrain.conf` (requires `sudo`)
- `.gitignore` — add `data/logs/`

---

### Work Item 2: Usage Data TTL with Configurable Retention

**Goal:** Automatically prune old LLM usage rows to keep `usage.db` bounded and queries fast.

**Approach:** Add a `prune_old_usage()` method to `UsageStore` that deletes rows older than a configurable retention period. Run it at the start of each daily sync.

**Behavior:**
- Default retention: **90 days** (configurable via `SECONDBRAIN_USAGE_RETENTION_DAYS` env var)
- Pruning runs once per daily sync, before extraction/inbox processing
- Deletes rows from `llm_usage` where `timestamp < datetime('now', '-N days')`
- Logs how many rows were deleted: `"Pruned 142 usage records older than 90 days"`
- Batch records (`extraction_batch`, `inbox_batch`) are pruned with the same TTL — they're regular rows

**Implementation:**
```python
# In UsageStore
def prune_old_usage(self, retention_days: int = 90) -> int:
    """Delete usage records older than retention_days. Returns count deleted."""
    sql = "DELETE FROM llm_usage WHERE timestamp < datetime('now', ?)"
    cursor = self.conn.execute(sql, (f"-{retention_days} days",))
    self.conn.commit()
    deleted = cursor.rowcount
    if deleted:
        logger.info("Pruned %d usage records older than %d days", deleted, retention_days)
    return deleted
```

```python
# In daily_sync.py main(), at the top before extraction
retention_days = int(os.environ.get("SECONDBRAIN_USAGE_RETENTION_DAYS", "90"))
usage_store.prune_old_usage(retention_days)
```

**Additionally:** Add a `make prune-usage` command for manual pruning:
```makefile
prune-usage:
    uv run python -c "from secondbrain.stores.usage import UsageStore; s = UsageStore('data/usage.db'); print(f'Pruned {s.prune_old_usage()} records')"
```

**Files:**
- `src/secondbrain/stores/usage.py` — `prune_old_usage()` method
- `src/secondbrain/scripts/daily_sync.py` — call prune at start of sync
- `Makefile` — `prune-usage` target
- `src/secondbrain/config.py` — `usage_retention_days: int = 90` setting (optional, could just use env var)

---

## Implementation Order

WI 1 and WI 2 are completely independent. Can be done in either order or in parallel.

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| **Docker** | Adds infrastructure complexity. Launchd + newsyslog achieves the same log persistence natively on macOS. Revisit for the public demo instance (Phase 8.9). |
| **Cloud deployment (Railway/Fly.io)** | Violates local-first principle. All vault content would go through a cloud provider. |
| **Centralized log aggregation (ELK, Loki)** | Overkill for a single-user system. Files + rotation are sufficient. |
| **Log level configuration UI** | Current Python `logging` config is fine. Not worth a UI. |
| **Separate archive table** | Just delete old rows. If we ever need historical analysis beyond 90 days, we'll export to CSV first. |

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| **newsyslog requires sudo** | Low — one-time setup | Document in setup instructions. Could use Python's `RotatingFileHandler` instead if sudo is undesirable, but that requires changing the logging config. |
| **Pruning deletes useful debug data** | Low — 90 days is generous for a single-user system | Configurable via env var. Can always increase. Run `make prune-usage` manually first to see what would be affected. |
| **Log files fill disk** | Low — rotation caps at ~18MB total (6 files * 3 copies) | newsyslog handles this automatically |

## Testing

**Automated:**
- Unit test for `prune_old_usage()`: insert rows with old timestamps, prune, verify correct count deleted and recent rows preserved
- Unit test: verify pruning with 0 old rows returns 0 (no-op)

**Manual QA:**
- Restart backend, check that `data/logs/api.stdout.log` captures startup messages
- Run `make prune-usage` on the live database, verify it reports a count and recent data is intact
- Verify `newsyslog` rotation works: `sudo newsyslog -nv` (dry-run to see what would rotate)

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **newsyslog over logrotate** | macOS native. logrotate isn't installed by default. newsyslog is the system standard. |
| **90-day default TTL** | Generous enough for debugging any recent issue. Anomaly detection uses 7-day windows, so 90 days gives 12x headroom. |
| **Prune in daily sync, not a separate cron** | One fewer launchd plist to maintain. Daily sync already runs all background maintenance. |
| **Delete over archive** | KISS. If we need historical data beyond 90 days, we'll know before it happens and can export first. |
| **Launchd plist log paths over Python RotatingFileHandler** | Captures ALL output (including uncaught exceptions, startup errors, library warnings) — not just what goes through Python's logging module. |
