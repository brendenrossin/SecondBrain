# Server Hardening — Eliminate Silent Failures and Relative Path Fragility

> **Status:** Planned (Phase 8.6)
> **Estimated effort:** 1 day
> **Depends on:** None (standalone hardening)

## Problem

The server silently returns empty data when misconfigured, making configuration errors look like data deletion. Two root causes:

1. **Relative paths in config:** `config.py` uses `env_file=".env"` and `data_path=Path("data")` — both resolve relative to the process's current working directory. If the server starts from a subdirectory (e.g., `frontend/` after `npm run build`), `.env` isn't found, vault_path defaults to `None`, and all APIs return empty.

2. **Silent empty returns:** The tasks, events, and briefing APIs return HTTP 200 with empty arrays when vault_path is `None`, instead of raising errors. The frontend renders "All clear — nothing due" which looks identical to a healthy empty state.

**Real incident:** On 2026-02-13, the implementation agent started the server from `frontend/` after a build. All APIs returned empty. Looked like all 49 tasks had been deleted. See `docs/devlog/errors/2026-02-13-server-cwd-env-file-silent-failure.md`.

## Solution

Four targeted changes that make the server robust regardless of working directory and loud about misconfigurations.

---

### Work Item 1: Make Config Paths Absolute

**Goal:** `.env` loading and `data_path` default work regardless of process cwd.

**File:** `src/secondbrain/config.py`

**Changes:**
- Add `_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent` at module level (`config.py` is at `src/secondbrain/config.py`, so three `.parent` calls reach the project root)
- Change `env_file=".env"` to `env_file=str(_PROJECT_ROOT / ".env")`
- Change `data_path: Path = Path("data")` to `data_path: Path = _PROJECT_ROOT / "data"`

**Testing:** Start the server from `frontend/` directory, verify `GET /api/v1/tasks` returns tasks (not empty).

---

### Work Item 2: Add Startup Configuration Logging

**Goal:** Misconfigurations are immediately visible in server logs.

**File:** `src/secondbrain/main.py`

**Changes:**
- Add a startup event (or extend existing one) that logs resolved configuration:
  ```
  SecondBrain starting — vault_path=/Users/.../main-vault, data_path=/Users/.../data
  ```
- If vault_path is None or doesn't exist, log an ERROR-level message:
  ```
  VAULT PATH NOT CONFIGURED OR MISSING — APIs will return errors
  ```
- Use `logger.warning` for the config line (visible in default log levels)

**Testing:** Restart server, check `/tmp/secondbrain-api.log` for the startup line.

---

### Work Item 3: Replace Silent Empty Returns with HTTP Errors

**Goal:** When vault_path is missing, APIs raise 503 instead of returning fake-empty data.

**Files and changes:**

- **`src/secondbrain/api/tasks.py` (line ~33-35):**
  Replace `return []` with `raise HTTPException(status_code=503, detail="Vault path not configured or not found")`

- **`src/secondbrain/api/events.py` (line ~40-42):**
  Replace `return []` with `raise HTTPException(status_code=503, detail="Vault path not configured or not found")`

- **`src/secondbrain/api/briefing.py` (line ~54-66):**
  Replace the empty `BriefingResponse(...)` return with `raise HTTPException(status_code=503, detail="Vault path not configured or not found")`

- Ensure `HTTPException` is imported from `fastapi` in each file (already imported in tasks.py, verify in others)

**Reference:** This matches the pattern already used in `api/index.py` and the tasks update endpoint (`tasks.py:91-93`).

**Testing:** Temporarily set vault_path to a nonexistent path, verify APIs return 503 with descriptive error, not 200 with empty data.

---

### Work Item 4: Remove Redundant Path Fallbacks

**Goal:** Clean up defensive fallbacks that are no longer needed after WI1.

**File:** `src/secondbrain/api/dependencies.py` (line ~43)

**Change:**
```python
# FROM:
data_path = Path(settings.data_path) if settings.data_path else Path("data")

# TO:
data_path = Path(settings.data_path)
```

The conditional fallback to `Path("data")` is no longer needed since `config.py` now provides an absolute default. The fallback was itself a relative-path bug waiting to happen.

---

## Implementation Order

```
Work Item 1: Absolute config paths (eliminates the root cause)
    └── Work Item 4: Remove fallbacks (cleanup, depends on WI1)
Work Item 2: Startup logging (independent)
Work Item 3: HTTP error responses (independent)
```

All four are independent enough to do in a single pass.

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| **Frontend error handling for 503** | The frontend should already handle non-200 responses. If it doesn't, that's a separate ticket. |
| **Health check vault verification** | Adding vault checks to `/health` could cause monitoring noise. Health checks should verify the server process, not external dependencies. |
| **Centralized config validation** | A full startup validation system is over-engineering for a single-user app. Startup logging (WI2) covers the need. |

## Testing

**Automated:**
- Test that `Settings()` resolves `.env` from an absolute path (mock cwd to a different directory)
- Test that tasks/events/briefing APIs raise `HTTPException(503)` when vault_path is None

**Manual QA:**
- Start server from `frontend/` directory → verify APIs still work (WI1)
- Start server with invalid vault path → check logs show ERROR message (WI2)
- Start server with invalid vault path → verify APIs return 503, not 200 with empty data (WI3)

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **503 over 500 for missing vault** | 503 (Service Unavailable) signals a configuration/infrastructure issue, not a code bug. Appropriate for "server is running but can't serve data." |
| **`Path(__file__).parent.parent.parent` for project root** | More reliable than `os.getcwd()`. The file's location in the source tree is fixed. |
| **Warning-level startup log** | INFO might be filtered by log config. WARNING ensures it appears in default output. |
| **No env var for project root** | Adding `SECONDBRAIN_PROJECT_ROOT` would just move the problem. Deriving from `__file__` is zero-config. |

## Known Minor Issues

_To be populated during implementation review._

| Issue | Severity | Notes |
|-------|----------|-------|

---

## Implementation Agent Prompt

You are implementing **Server Hardening** for SecondBrain. Read the full spec at `docs/features/server-hardening.md` and the error log at `docs/devlog/errors/2026-02-13-server-cwd-env-file-silent-failure.md` for context.

**Implementation order — follow this sequence:**

#### Step 1: Make config paths absolute (WI1)

**File:** `src/secondbrain/config.py`

1. Add at the top of the file (after imports):
   ```python
   _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
   ```
2. In the `SettingsConfigDict`, change:
   ```python
   env_file=".env",
   ```
   to:
   ```python
   env_file=str(_PROJECT_ROOT / ".env"),
   ```
3. Change the `data_path` default:
   ```python
   # FROM:
   data_path: Path = Path("data")
   # TO:
   data_path: Path = _PROJECT_ROOT / "data"
   ```

#### Step 2: Add startup logging (WI2)

**File:** `src/secondbrain/main.py`

Add a startup event that logs resolved configuration. Check if there's already a `@app.on_event("startup")` handler — if so, add to it. If not, create one:

```python
import logging
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def log_startup_config():
    from secondbrain.config import get_settings
    s = get_settings()
    logger.warning("SecondBrain starting — vault_path=%s, data_path=%s", s.vault_path, s.data_path)
    if not s.vault_path or not s.vault_path.exists():
        logger.error("VAULT PATH NOT CONFIGURED OR MISSING — APIs will return 503 errors")
```

If `main.py` already uses lifespan context managers instead of `on_event`, use that pattern instead.

#### Step 3: Replace silent empty returns with 503 errors (WI3)

**File: `src/secondbrain/api/tasks.py`** — find the `_get_aggregated` function (line ~33-35):
```python
# FROM:
if not vault_path or not vault_path.exists():
    return []
# TO:
if not vault_path or not vault_path.exists():
    raise HTTPException(status_code=503, detail="Vault path not configured or not found")
```
Note: `_get_aggregated` is a regular function called by the route handler. Move the vault check into the route handler `list_tasks` instead (so the HTTPException propagates correctly from an async context), OR raise the exception from `_get_aggregated` — FastAPI will catch it either way. Just make sure `HTTPException` is imported (it already is in this file).

**File: `src/secondbrain/api/events.py`** — find the vault check (line ~40-42):
```python
# FROM:
if not vault_path or not vault_path.exists():
    return []
# TO:
if not vault_path or not vault_path.exists():
    raise HTTPException(status_code=503, detail="Vault path not configured or not found")
```
Ensure `HTTPException` is imported from `fastapi`.

**File: `src/secondbrain/api/briefing.py`** — find the vault check (line ~54-66):
```python
# FROM:
if not vault_path or not vault_path.exists():
    return BriefingResponse(
        today=today_str,
        today_display=today_display,
        overdue_tasks=[],
        ...
    )
# TO:
if not vault_path or not vault_path.exists():
    raise HTTPException(status_code=503, detail="Vault path not configured or not found")
```
Ensure `HTTPException` is imported from `fastapi`.

#### Step 4: Remove redundant fallback (WI4)

**File: `src/secondbrain/api/dependencies.py`** — find the `get_data_path` function (line ~43):
```python
# FROM:
data_path = Path(settings.data_path) if settings.data_path else Path("data")
# TO:
data_path = Path(settings.data_path)
```

#### Step 5: Verify

After all changes, restart the backend from the project root:
```
cd /Users/brentrossin/SecondBrain
kill -9 $(lsof -ti:8000) 2>/dev/null
export PATH="$HOME/.local/bin:$PATH"
nohup uv run uvicorn secondbrain.main:app --host 127.0.0.1 --port 8000 > /tmp/secondbrain-api.log 2>&1 &
sleep 3 && curl -s http://localhost:8000/health
```

Then verify:
1. `curl http://localhost:8000/api/v1/tasks` returns tasks (not empty)
2. Check `/tmp/secondbrain-api.log` for the startup config line
3. `curl http://localhost:8000/api/v1/briefing` returns real data

Follow the commit workflow: write code -> `/test-generation` -> `code-simplifier` -> commit.
