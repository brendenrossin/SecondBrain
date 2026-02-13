# Error: Server Started from Wrong Directory — Silent Empty API Responses

**Date:** 2026-02-13
**Severity:** Critical
**Component:** Backend API server startup / pydantic-settings config loading

## Symptoms

- Home page showed "0 open tasks", 0 Overdue, 0 Due Today, 0 Aging, 0 Total Open
- "All clear — No overdue tasks, nothing due today, and no aging follow-ups" displayed
- Tasks page returned empty list
- Calendar showed no events or tasks
- Admin costs/daily API returned `{"days": 30, "daily": []}`
- Briefing API returned all empty arrays and `total_open: 0`
- **No errors in server logs** — all requests returned HTTP 200
- Appeared as if all data had been deleted

## Root Cause

The backend API server was restarted from `/Users/brentrossin/SecondBrain/frontend/` instead of the project root `/Users/brentrossin/SecondBrain/`.

**The chain of failure:**

1. The implementation agent ran `cd /Users/brentrossin/SecondBrain/frontend && npm run build` to rebuild the frontend
2. After the build, the agent restarted the backend server **without changing back to the project root**
3. `config.py` uses `env_file=".env"` — a **relative path** resolved against the process's current working directory
4. Pydantic-settings looked for `/Users/brentrossin/SecondBrain/frontend/.env` — which doesn't exist
5. Without `.env`, `vault_path` defaulted to `None` (its default in the Settings model)
6. The tasks API (`tasks.py` line 34) has `if not vault_path or not vault_path.exists(): return []` — so it silently returned an empty list
7. The briefing API hit the same condition and returned all zeros
8. The usage store's `data_path` (relative `data`) resolved to `frontend/data/` instead of `data/`, so cost queries returned empty

**Critical detail:** The server returned HTTP 200 with valid-looking empty JSON on every endpoint. Health check passed. No errors logged. This made it look like a data deletion rather than a configuration failure.

## Fix Applied

Restarted the server from the correct working directory:

```bash
cd /Users/brentrossin/SecondBrain
kill -9 $(lsof -ti:8000) 2>/dev/null
export PATH="$HOME/.local/bin:$PATH"
nohup uv run uvicorn secondbrain.main:app --host 127.0.0.1 --port 8000 > /tmp/secondbrain-api.log 2>&1 &
```

All 49 tasks, events, and cost data immediately reappeared. No data was ever lost.

## Files Modified

No code changes — this was a process restart fix. Documentation updated:
- `~/.claude/projects/-Users-brentrossin-SecondBrain/memory/MEMORY.md` — added critical warning about server cwd requirement

## How to Prevent

1. **Always `cd /Users/brentrossin/SecondBrain` before restarting the backend server.** Add this explicitly to every restart instruction block.
2. **Longer-term code fix:** Change `config.py` to use an absolute path for `env_file`:
   ```python
   env_file=Path(__file__).resolve().parent.parent.parent / ".env"
   ```
   This would resolve `.env` relative to the project root regardless of cwd.
3. **Add a startup log line** that prints the resolved vault_path and data_path so misconfigurations are visible immediately.
4. **Add a warning or non-200 response** when vault_path is None instead of silently returning empty arrays. A 503 "vault not configured" would surface this instantly.

## Lessons Learned

- **Relative `env_file` paths in pydantic-settings are a footgun.** In a project where you routinely `cd` into subdirectories (frontend builds, test runs), the server's cwd can easily drift.
- **Silent success is worse than loud failure.** The server returned 200 with empty JSON — the most dangerous kind of bug because it looks like data loss. A single warning log or a non-200 response would have saved 10 minutes of panic debugging.
- **Implementation agents need explicit `cd` in their restart commands.** The restart instructions in MEMORY.md didn't include `cd` to project root, and the agent had already `cd`'d to `frontend/` for the build step.
- **Vault data is never at risk from server issues.** The vault (Obsidian markdown files) is the source of truth. The server is a read-only view. Even when the server appears empty, the vault is untouched. This is a vindication of the "vault is source of truth" architecture.

## Detection

- **Discovered by:** User opened the app and saw all zeros on the home page
- **Diagnosis time:** ~5 minutes (checked database directly → data present → API returns empty → checked server cwd → found the mismatch)
- **Earlier detection:** A startup log line printing `vault_path={settings.vault_path}` would have surfaced this immediately in `/tmp/secondbrain-api.log`
