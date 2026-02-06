# Feature: Task Sync Enhancements, Project Integration, Incremental Indexing

**Date:** 2026-02-06
**Branch:** main

## Summary

Added four features in one batch: Timeline column header for task tables, bi-directional due date sync between daily notes and the aggregate task file, automatic project file integration that populates `20_Projects/*.md` with matching tasks and recent notes, and incremental indexing that only re-chunks/embeds changed files instead of doing a full rebuild every time.

## Problem / Motivation

1. **Timeline column** was unnamed — confusing in Obsidian reading mode.
2. **Due dates** only flowed daily→aggregate. Users who edited due dates in All Tasks.md couldn't get those changes back into daily notes.
3. **Project files** in `20_Projects/` were manually maintained. No automatic view of which tasks and notes related to each project.
4. **Full reindex** on every sync was wasteful — reading, chunking, and embedding 100+ unchanged notes when only 1-2 changed.

## Solution

- **Timeline column**: Single string replacement in `_write_aggregate_file()`.
- **Due date sync**: New `_read_aggregate_due_dates()` parses the Due column from All Tasks.md. Extended `_sync_completions_to_daily()` → `_sync_changes_to_daily()` to also sync non-empty due dates back to daily notes.
- **Project sync**: New `project_sync.py` module. Matches tasks to project files via normalized fuzzy name matching (strip punctuation + whitespace, substring check). Scans `## Notes` sections of recent daily notes for project mentions. Writes auto-generated sections with `<!-- AUTO-GENERATED -->` markers, preserving all manual content.
- **Incremental indexing**: New `IndexTracker` SQLite store tracks `(file_path, content_hash, last_modified)`. On reindex, classifies files as new/modified/deleted/unchanged using mtime as fast pre-filter and SHA1 hash as deterministic check. Only re-chunks and embeds new+modified files; deletes chunks for deleted files.

## Files Modified

**Task Aggregator (modified)**
- `src/secondbrain/scripts/task_aggregator.py` — Timeline header, `_read_aggregate_due_dates()`, renamed `_sync_changes_to_daily()` with due date support, made `scan_daily_notes()` and `aggregate_tasks()` public

**Project Sync (new)**
- `src/secondbrain/scripts/project_sync.py` — Full module: name normalization, matching, note extraction, auto-section management, project file updates

**Incremental Indexing (new + modified)**
- `src/secondbrain/stores/index_tracker.py` — New SQLite tracker with WAL/busy_timeout/reconnect pattern
- `src/secondbrain/vault/connector.py` — Added `get_file_metadata()` returning `{path: (mtime, sha1)}`
- `src/secondbrain/stores/vector.py` — Added `delete_by_note_path()` using ChromaDB `where` filter
- `src/secondbrain/api/dependencies.py` — Rewrote `check_and_reindex()` for incremental flow
- `src/secondbrain/api/index.py` — Added `full_rebuild` query param, incremental by default

**Daily Sync (modified)**
- `src/secondbrain/scripts/daily_sync.py` — Added `projects` command, integrated `sync_projects()`

**Tests (new + modified)**
- `tests/test_task_aggregator.py` — Due date sync tests, updated imports for public functions
- `tests/test_project_sync.py` — New: name matching, note extraction, section management, integration
- `tests/test_index_tracker.py` — New: classify, persistence, reconnect tests
- `tests/test_stores.py` — Added `VectorStore.delete_by_note_path()` tests

## Key Decisions & Trade-offs

1. **Due date sync is add-only, not bidirectional delete**: If the aggregate has no due date, the daily note's date is preserved. This prevents the sync loop from clobbering user-added dates before the aggregate regenerates. Users remove dates directly in daily notes.

2. **Project name matching uses substring after normalization**: `normalize_project_name()` strips `.md`, lowercases, removes punctuation AND whitespace — so "SecondBrain" matches "Second Brain". Simple but effective for typical project names.

3. **Auto-generated section markers**: `<!-- AUTO-GENERATED -->` / `<!-- END AUTO-GENERATED -->` delimit managed content. Everything outside markers (user's manual notes, architecture sections) is preserved across syncs.

4. **Incremental indexing uses mtime as fast pre-filter, SHA1 as truth**: If mtime unchanged, skip hash comparison. If mtime changed but hash same (file touched but not modified), classify as unchanged. Only re-embed when content actually changed.

5. **First run == full rebuild**: Empty tracker classifies all files as "new", so incremental indexing gracefully handles fresh installs.

## Patterns Established

- **Public API for task scanning**: `scan_daily_notes()` and `aggregate_tasks()` are now public (no underscore) for reuse by project_sync and future modules.
- **Auto-generated section pattern**: `_update_auto_section()` can insert or replace content between markers in any markdown file — reusable for future auto-generated sections.
- **IndexTracker follows same store patterns**: WAL mode, busy_timeout=5000, reconnect-on-error — consistent with LexicalStore and ConversationStore.
- **`delete_by_note_path()`**: Both VectorStore and LexicalStore now support deleting all chunks for a given note path — essential for incremental reindexing.

## Testing

- 122 tests pass (up from ~90 before this batch)
- New test files: `test_index_tracker.py` (11 tests), `test_project_sync.py` (17 tests)
- Extended: `test_task_aggregator.py` (+7 due date tests), `test_stores.py` (+3 vector delete tests)
- All lint-clean on new code (3 pre-existing SIM105 warnings in unchanged files)

## Future Considerations

- **Embedding cache by content hash**: Natural follow-up to incremental indexing — if a file's chunks match previously computed embeddings (by chunk text hash), skip the embedding call entirely.
- **LLM-based project matching**: Current substring matching is simple. Phase 3 metadata extraction could enable smarter matching.
- **File watcher**: Real-time incremental indexing via watchdog instead of trigger-file polling.
- **Due date deletion from aggregate**: Currently aggregate can only add/change dates, not remove them. Could add a convention like clearing the cell to signal deletion, but needs careful UX consideration.
