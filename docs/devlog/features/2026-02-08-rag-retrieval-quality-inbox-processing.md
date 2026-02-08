# Feature: RAG Retrieval Quality + Inbox Processing Improvements

**Date:** 2026-02-08
**Branch:** main

## Summary

Comprehensive improvement to both the RAG retrieval pipeline and the inbox processing system. The retrieval side adds heading context to embeddings, structural metadata (folder/date) to chunks, enriches the reranker and synthesis LLM with temporal context, and excludes noisy files from the index. The inbox side adds safe file handling (archive-not-delete), LLM output validation with retry, multi-topic segmentation, duplicate detection, and living document support with replace/append semantics.

## Problem / Motivation

**RAG issues (eval baseline: Precision@5 35.1%, Recall@5 78.3%):**
- Embeddings saw raw chunk text only — no heading context (e.g. "Review MCP client" under "AT&T > AI Receptionist" had no structural signal)
- heading_path was stored in SQLite but NOT in FTS5, so BM25 couldn't match heading structure
- `Tasks/All Tasks.md` dominated search results due to high keyword density, crowding out source notes
- `Inbox/` raw dictation was indexed before processing
- Reranker and synthesis LLM had no date/folder context for temporal queries ("what did I do yesterday?")
- Stale index: daily sync wrote trigger file but server only consumed it on next query, causing retrieval failures for recently-synced content

**Inbox issues:**
- Original file deleted even on LLM failure — data loss with no recovery path
- No validation of LLM structured output (trusts blindly)
- No duplicate detection
- Cannot split multi-topic dictation into separate segments
- No support for living documents (grocery lists, recipe collections)

## Solution

### Workstream B: RAG Retrieval (Phases 1-2)

1. **B1 — Exclude problem files:** Added `Inbox/*`, `Tasks/All Tasks.md`, `Tasks/Completed Tasks.md` to `VaultConnector.DEFAULT_EXCLUDES`. Updated eval queries to reference source daily notes instead.
2. **B2 — FTS5 heading_path:** Added `heading_path` column to FTS5 virtual table with automatic schema versioning. When schema version changes, FTS5 table is dropped and recreated, then rebuilt from content table.
3. **B3 — Heading context in embeddings:** `build_embedding_text(chunk)` prepends `heading_path` as "Tasks > AT&T > AI Receptionist\n{chunk_text}". Applied in both indexing pipelines (API endpoint + trigger-file reindex).
4. **B4 — Note metadata:** Added `note_folder` and `note_date` fields to Chunk model. Extracted from path (first folder component) and frontmatter date/daily note filename pattern. Stored in both ChromaDB metadata and SQLite.
5. **B5 — Enriched reranker/synthesis:** `RetrievalCandidate` now carries `note_folder` and `note_date`. Reranker sees `[1] [00_Daily] (2026-02-05) Daily Note > Tasks > AT&T`. Synthesis system prompt instructs LLM to use dates for temporal queries.
6. **Stale index fix:** `daily_sync.py` now attempts an HTTP POST to the running server's `/api/v1/index` after writing the trigger file. If server is down, trigger file persists for next startup.

### Workstream A: Inbox Processing (Phases 3-4)

1. **A1 — Safe file handling:** Files move to `Inbox/_processed/` on success, `Inbox/_failed/` on failure — never deleted. Timestamp suffix prevents name collisions.
2. **A1 — Validation + retry:** `_validate_classification()` checks note_type enum and task list types. `_classify_with_retry()` retries once on validation failure or JSON parse error.
3. **A1 — Duplicate detection:** SHA-1 hash comparison against files in `_processed/` directory.
4. **A2 — Multi-topic segmentation:** Two-pass architecture — `_segment_content()` uses LLM to split rambling dictation into logical segments (conservative: "when in doubt, keep together"). Each segment then classified independently. Short texts (<300 chars) skip segmentation.
5. **A3a — Living documents:** Hardcoded registry of known living documents (Grocery List: replace, Recipe Ideas: append). Replace semantics archives old content under `## Archive > ### YYYY-MM-DD`. Append adds under date-stamped heading. Unknown living docs fall back to regular note routing.

## Files Modified

### RAG Pipeline
- `src/secondbrain/vault/connector.py` — Added exclude patterns
- `src/secondbrain/stores/lexical.py` — FTS5 schema versioning, heading_path in FTS5, note_folder/note_date columns, column migration
- `src/secondbrain/stores/vector.py` — note_folder/note_date in ChromaDB metadata
- `src/secondbrain/models.py` — note_folder/note_date fields on Chunk
- `src/secondbrain/indexing/embedder.py` — `build_embedding_text()`, `extract_note_metadata()`
- `src/secondbrain/api/dependencies.py` — Metadata population + heading-context embedding in reindex
- `src/secondbrain/api/index.py` — Same for API-triggered indexing
- `src/secondbrain/retrieval/hybrid.py` — note_folder/note_date on RetrievalCandidate
- `src/secondbrain/retrieval/reranker.py` — Enriched chunk context with folder/date, updated system prompt
- `src/secondbrain/synthesis/answerer.py` — Enriched context, temporal instruction in system prompt
- `src/secondbrain/eval/eval_queries.yaml` — Removed All Tasks.md references, added concept note queries
- `src/secondbrain/scripts/daily_sync.py` — HTTP reindex call after trigger file

### Inbox Processing
- `src/secondbrain/scripts/inbox_processor.py` — Full rewrite: segmentation, validation, retry, duplicate detection, living documents, archive-not-delete
- `tests/test_inbox_processor.py` — 18 new tests (156 -> 174 total)

## Key Decisions & Trade-offs

1. **FTS5 schema versioning over ALTER TABLE:** FTS5 virtual tables can't be altered — we track a schema version in a `schema_meta` table and drop/recreate when it changes. This is clean but requires a full FTS rebuild on upgrade.

2. **Heading context on document-side only:** `build_embedding_text()` prepends heading path to documents but NOT to queries. This is intentional — the user's query "AI Receptionist" should match the heading context without needing to repeat it.

3. **LLM-driven recency over decay formula:** Instead of applying a time-decay multiplier to scores, we pass dates to the LLM and let it reason about temporal relevance. This is more flexible (handles "last week" vs "yesterday" vs "most recent") and avoids tuning a decay constant.

4. **Two-pass segmentation, not multi-agent:** The segmentation is just two sequential LLM calls in one function — not an agent framework. Conservative splitting ("when in doubt, keep together") means single-topic notes pass through unchanged with minimal overhead.

5. **Archive-not-delete for inbox:** Processed files preserved in `_processed/` rather than deleted. This was the #1 safety issue flagged in ENGINEERING_REVIEW.md. The cost is disk space, which is negligible for text files.

6. **Living documents hardcoded (A3a), not YAML registry (A3b):** Shipped minimal version with just Grocery List and Recipe Ideas. YAML registry deferred until more living docs are needed — avoids premature abstraction.

7. **HTTP reindex call in daily sync:** Uses stdlib `urllib.request` (no new dependency) with a try/except so a down server doesn't break the sync. The 120s timeout is generous to allow full reindex completion.

## Patterns Established

- **FTS5 schema versioning:** Use `schema_meta` table with `fts_schema_version` key. Bump `_FTS_SCHEMA_VERSION` class variable when changing FTS5 columns.
- **Column migration:** Use `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` pattern for backward-compatible SQLite schema changes.
- **`build_embedding_text()`:** All indexing paths must use this helper instead of raw `chunk_text` for embedding. Both `api/dependencies.py` and `api/index.py` call it.
- **`extract_note_metadata()`:** Centralized folder/date extraction from note path and frontmatter.
- **Inbox safety pattern:** `_move_to_subfolder()` for all inbox file disposition. Never `unlink()`.
- **LLM output validation:** Always validate structured LLM output before acting on it. Use `_classify_with_retry()` pattern for critical paths.

## Testing

- 174 tests pass (18 new), lint clean, mypy clean
- New test classes: `TestMoveToSubfolder`, `TestValidateClassification`, `TestValidateSegments`, `TestDuplicateDetection`, `TestRouteLivingDocument`, `TestProcessInbox.test_failed_processing_moves_to_failed`
- **Full reindex required** after deployment (`make reindex`) to regenerate embeddings with heading context and populate note_folder/note_date metadata
- Run `make eval` before and after reindex to measure Precision@5 improvement (target: >45%)

## Future Considerations

- **A3b (YAML registry):** When more living documents are needed, extract hardcoded list into `_config/living_documents.yaml` and inject dynamically into the classification prompt
- **A4 (Model quality eval):** Test Ollama gpt-oss:20b vs OpenAI gpt-4o-mini accuracy for segmentation and classification. If Ollama <80%, consider OpenAI as primary for inbox.
- **Eval expansion:** Current eval doesn't test reranker or synthesis — only HybridRetriever. Should add end-to-end eval and per-tag metric breakdowns.
- **Processed file cleanup:** `Inbox/_processed/` will accumulate files. Consider a retention policy (delete after 30 days).
- **Chunker improvements:** Now that embeddings have heading context, evaluate whether larger chunk sizes (1000-1500 chars) improve retrieval quality.
