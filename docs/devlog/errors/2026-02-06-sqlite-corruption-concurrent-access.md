# Error: FTS5 Corruption from Content-Sync Triggers + INSERT OR REPLACE

**Date:** 2026-02-06
**Severity:** Critical
**Component:** LexicalStore (SQLite FTS5), VectorStore (ChromaDB)

## Symptoms

- UI queries returning `database disk image is malformed` after reindex
- First query after UI restart worked; running daily sync; next query errored
- Repeated reindexes (even within a single process) corrupted FTS5 search

## Root Cause (Final — 5 iterations to identify)

**Two distinct problems required two distinct fixes:**

### Problem 1: Multi-Process Store Access
Daily sync (separate launchd job) and UI server (always-on launchd) both created their own store instances pointing to the same files. ChromaDB `PersistentClient` is explicitly single-process only, and SQLite without WAL mode doesn't handle concurrent writers.

### Problem 2: FTS5 Content-Sync Triggers + INSERT OR REPLACE (the real killer)
This was the true root cause of persistent corruption, even after fixing multi-process access.

The FTS5 table was configured with **external content sync** (`content='chunks'`) and **triggers** to keep the index in sync. When `INSERT OR REPLACE` ran on the `chunks` table, it fired a DELETE trigger then an INSERT trigger on the FTS5 shadow tables. This sequence **corrupts FTS5 shadow tables** — a known SQLite FTS5 pitfall.

From the SQLite docs: *"External content FTS5 tables do not support REPLACE conflict handling."*

**Key insight:** The corruption happened within a single process. The multi-process theory was a red herring for FTS5 — we spent 4 iterations chasing it before discovering the triggers were the real issue.

## Debugging Timeline

1. **Attempt 1:** WAL mode + busy timeout → still corrupted (ChromaDB was also a problem)
2. **Attempt 2:** Added ChromaDB reconnect + epoch invalidation → error on first query (old corrupt DB)
3. **Attempt 3:** Clean rebuild of lexical.db → broke again after daily sync (multi-process FTS5 writes)
4. **Attempt 4:** Single-process architecture (trigger file) → still broke (corruption from triggers within same process)
5. **Attempt 5 (final):** Removed FTS5 triggers, use explicit `rebuild` command after writes → fixed

## Fix Applied

### Layer 1: Single-Process Store Architecture
- Daily sync no longer touches stores directly
- Writes a trigger file (`data/.reindex_needed`) with the vault path
- UI detects trigger before each query via `check_and_reindex()` and performs reindex using its own cached store instances
- Eliminates all multi-process store access

### Layer 2: FTS5 Triggers Removed, Explicit Rebuild
- Removed all three FTS5 content-sync triggers (`chunks_ai`, `chunks_ad`, `chunks_au`)
- Added `DROP TRIGGER IF EXISTS` in schema init to clean up existing databases
- Kept `content='chunks'` (external content) — FTS5 reads from chunks table
- After every write to the chunks table, call `_rebuild_fts()`:
  ```python
  self.conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
  ```
- This is the approach explicitly recommended by SQLite docs: *"the application may arrange to call the rebuild command after all writes to the content table are complete"*

### Layer 3: WAL Mode + Busy Timeout + Reconnect-on-Error
- `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` on all SQLite connections
- Reconnect-on-error pattern on all stores (LexicalStore, ConversationStore, VectorStore)
- Epoch-based proactive invalidation for detecting external changes

## Files Modified

- `src/secondbrain/stores/lexical.py` — removed triggers, added `_rebuild_fts()`, WAL, reconnect, epoch
- `src/secondbrain/stores/conversation.py` — WAL, busy timeout, reconnect
- `src/secondbrain/stores/vector.py` — reconnect-on-error, epoch checking
- `src/secondbrain/scripts/daily_sync.py` — trigger-file architecture (no direct store access)
- `src/secondbrain/api/dependencies.py` — `check_and_reindex()` function
- `src/secondbrain/ui.py` — calls `check_and_reindex()` before retrieval
- `tests/test_stores.py` — 23 tests including FTS5 integrity regression tests

## Key Tests

- `test_repeated_reindex_does_not_corrupt_fts`: 5 consecutive INSERT OR REPLACE cycles + FTS5 integrity check
- `test_add_delete_add_cycle`: add/delete/add cycle verifying FTS consistency
- `test_no_triggers_exist`: confirms legacy triggers are dropped

## Lessons Learned

- **Don't use FTS5 triggers with INSERT OR REPLACE.** The SQLite docs explicitly warn about this.
- **Multi-process was a red herring** for the FTS5 corruption — always verify the true root cause before assuming
- **ChromaDB PersistentClient is single-process only** — not obvious from the API
- **Single-writer architecture** (trigger file + UI does reindex) eliminates an entire class of concurrency bugs
- **The `rebuild` command is safe and atomic** — it reads from the content table and reconstructs FTS5 without trigger involvement
- When debugging data corruption, question every assumption — the first plausible theory may not be the right one
