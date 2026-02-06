# Feature: Phase 3 — Metadata Extraction + Suggestions

**Date:** 2026-02-06
**Branch:** main

## Summary

Added LLM-based metadata extraction and a suggestion engine to turn SecondBrain from a search tool into a memory assistant. The system now extracts structured metadata (summaries, entities, dates, action items) from vault notes and generates actionable suggestions (related notes, wiki-links, tags).

## Problem / Motivation

Phases 0-2 delivered hybrid search and answer synthesis, but the system was passive — users had to know what to ask. Phase 3 makes the system proactive: it understands note content structurally and can suggest connections, missing links, and relevant tags that the user might not think to search for.

## Solution

- **LLM-only extraction** (no spaCy): one LLM call per note via existing `LLMClient` (Ollama-first, OpenAI-fallback). Regex only for date normalization.
- **Note-level extraction**: summaries, key phrases, entities, dates, and action items extracted per note (not per chunk), keeping LLM costs low.
- **Separate extraction step**: decoupled from indexing to keep indexing fast. Runs via API, CLI, or daily sync.
- **Incremental**: content hash comparison skips notes whose content hasn't changed.
- **On-demand suggestions**: computed when requested using existing vector store, not pre-computed.
- **Read-only**: suggestions are displayed but not applied to files (write-back deferred to Phase 7).

## Files Modified

**New modules:**
- `src/secondbrain/stores/metadata.py` — SQLite WAL store for extracted metadata
- `src/secondbrain/extraction/__init__.py` + `extractor.py` — LLM extraction pipeline
- `src/secondbrain/suggestions/__init__.py` + `engine.py` — Related notes, link, and tag suggestions
- `src/secondbrain/api/metadata.py` — 6 API endpoints for metadata, extraction, suggestions

**New tests:**
- `tests/test_metadata_store.py` — 11 tests for store CRUD, staleness, reconnect
- `tests/test_extractor.py` — 17 tests for date normalization, prompt building, parsing, batch extraction
- `tests/test_suggestions.py` — 6 tests for related notes, shared entities, link and tag suggestions

**Modified:**
- `src/secondbrain/models.py` — 8 new Pydantic models
- `src/secondbrain/config.py` — `metadata_db_name` setting
- `src/secondbrain/api/dependencies.py` — factories for MetadataStore, LLMClient, MetadataExtractor, SuggestionEngine
- `src/secondbrain/main.py` — registered metadata router
- `src/secondbrain/ui.py` — Insights + Suggestions tabs in Gradio UI
- `src/secondbrain/scripts/daily_sync.py` — extraction step after reindex, `extract` command
- `src/secondbrain/scripts/llm_client.py` — added `model_name` public attribute
- `Makefile` — `make extract` target
- `docs/ROADMAP.md` — Phase 3 marked complete

## Key Decisions & Trade-offs

1. **LLM-only, no spaCy**: spaCy would add ~100MB+ for NER that an LLM already handles well. Single JSON prompt extracts everything in one call. Trade-off: extraction is slower per note but avoids dependency bloat.

2. **Note-level, not chunk-level**: 1 LLM call per note vs 5-10 per chunk. Summaries and entities make more semantic sense at the note level. Long notes (>12K chars) are truncated.

3. **Separate MetadataStore (not in IndexTracker)**: extraction is optional and decoupled from indexing. Keeps indexing fast. Content hash comparison for staleness uses the same hashes the vault connector already computes.

4. **On-demand suggestions (not pre-computed)**: vector search + metadata lookups are fast enough (<100ms). Pre-computing for all note pairs would be O(n^2) storage for marginal UX gain.

5. **Daily sync runs extraction in-process**: unlike reindexing (which uses a trigger file because ChromaDB is single-process), metadata extraction only touches SQLite, so it runs directly in the sync process.

6. **`model_name` public attribute on LLMClient**: the code simplifier flagged that the extractor was accessing `llm_client._settings.ollama_model` via private attribute. Added a clean public API instead.

## Patterns Established

- **Extraction module pattern**: `extraction/extractor.py` shows how to build an LLM-powered pipeline that produces structured Pydantic models from notes. Future extractors (e.g., for knowledge graph triples) should follow this pattern.
- **`_title_from_path` helper**: extracted in `suggestions/engine.py` for the common `path.rsplit("/", 1)[-1].replace(".md", "")` pattern.
- **`_execute` with auto-reconnect**: `MetadataStore._execute()` wraps all SQL with reconnect-on-error, cleaner than the per-method try/except in older stores.
- **Suggestion engine composition**: `SuggestionEngine` composes vector store + metadata store + embedder without owning any of them. Dependencies injected via `dependencies.py`.

## Testing

- 34 new tests across 3 test files (156 total, all passing)
- `MetadataStore`: CRUD, upsert-overwrites, staleness detection, reconnect-on-error
- `MetadataExtractor`: date normalization (ISO, US, short year), prompt building, truncation, JSON parsing with missing fields, batch extraction with progress and failure handling
- `SuggestionEngine`: related notes deduplication, self-exclusion, shared entity detection, link suggestions from entities, tag suggestions from related notes' key phrases
- Lint (`ruff check`) and typecheck (`mypy`) clean — no new errors introduced

## Future Considerations

- **Extraction speed**: batch extraction is sequential. Could parallelize with async or threading for large vaults (>500 notes).
- **Token counting**: `max_chars=12000` is a rough proxy. Could use tiktoken for accurate token counting if truncation becomes an issue.
- **Frontmatter tag integration**: tag suggestions currently use key phrases as proxy. Could read actual frontmatter tags for better suggestions.
- **Write-back (Phase 7)**: suggestions are read-only. Phase 7 will add the ability to apply suggested links/tags to vault files via a changeset workflow.
- **Entity deduplication**: "Alice Smith" and "Alice" are treated as separate entities. Could add fuzzy matching or coreference resolution.
