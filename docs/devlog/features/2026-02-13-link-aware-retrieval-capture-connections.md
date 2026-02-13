# Feature: Link-Aware Retrieval + Capture Connection Surfacing

**Date:** 2026-02-13
**Branch:** main

## Summary

Two related retrieval enhancements shipped together. Link-aware retrieval follows `[[wiki links]]` in retrieved chunks to inject supplementary context from the user's curated note graph into the answerer. Capture connection surfacing runs a quick hybrid search after every capture and shows related notes immediately in the frontend, turning fire-and-forget captures into knowledge moments.

## Problem / Motivation

**Link-aware retrieval:** The RAG pipeline only found chunks semantically or lexically similar to the query. It completely ignored the explicit `[[wiki links]]` the user created to connect related ideas. A query about "Project Alpha timeline" might retrieve a chunk containing `[[Q3 Planning Notes]]` — but that linked note (with critical planning context) would never surface because it isn't semantically similar to the query.

**Capture connections:** Quick capture was fire-and-forget. After capturing a thought, the user had no idea what related notes already existed in their vault. The moment of capture is when engagement is highest — showing "you've thought about this before" prevents duplication and surfaces forgotten context.

## Solution

**Link-aware retrieval (5 components):**
1. Wiki link parser (`vault/links.py`) — regex-based extraction of `[[Note]]`, `[[Note|alias]]`, `[[Note#heading]]` formats, with code block exclusion
2. Link resolver (`LexicalStore.resolve_note_path()`) — case-insensitive title-to-path lookup via the chunks table
3. Link expander (`retrieval/link_expander.py`) — iterates ranked candidates, parses wiki links, resolves paths, fetches first chunk per linked note, caps at 3
4. Answerer integration — appends "CONNECTED NOTES" section to context window with clear labeling
5. Pipeline wiring — injected via FastAPI `Depends()` into both `/ask` and `/ask/stream`

**Capture connections (4 components):**
1. `CaptureConnection` model + updated `CaptureResponse` with `connections: list[CaptureConnection] = []`
2. Backend: after file write, best-effort hybrid retrieval → dedup by note_path → top 5 → metadata summary snippets with chunk text fallback
3. Frontend types: `CaptureConnection` interface added to `types.ts`
4. Frontend cards: compact glass-card display with folder badge, title, snippet — clears on new input

## Files Modified

**Link-Aware Retrieval:**
- `src/secondbrain/vault/links.py` — Created (wiki link parser)
- `src/secondbrain/stores/lexical.py` — Added `resolve_note_path()`, `get_first_chunk()`
- `src/secondbrain/retrieval/link_expander.py` — Created (LinkExpander + LinkedContext)
- `src/secondbrain/synthesis/answerer.py` — Updated `_build_context()`, `SYSTEM_PROMPT`, method signatures
- `src/secondbrain/api/ask.py` — Wired link expander via `Depends()`
- `src/secondbrain/api/dependencies.py` — Added `get_link_expander()`

**Capture Connections:**
- `src/secondbrain/models.py` — Added `CaptureConnection`, updated `CaptureResponse`
- `src/secondbrain/api/capture.py` — Added retrieval + metadata lookup after file write
- `frontend/src/lib/types.ts` — Added `CaptureConnection`, updated `CaptureResponse`
- `frontend/src/components/capture/CaptureForm.tsx` — Added connection card display

**Tests:**
- `tests/test_links.py` — 13 tests (parser)
- `tests/test_link_expander.py` — 7 tests (expander)
- `tests/test_answerer_links.py` — 5 tests (context building)
- `tests/test_capture_api.py` — 7 new tests (connections)

## Key Decisions & Trade-offs

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Runtime link parsing vs. indexing-time storage | Runtime | Avoids schema changes and reindexing. SQLite lookups are <10ms. Optimize later if needed. |
| 1-hop only, no multi-hop | 1-hop | Complexity explosion with multi-hop. One hop covers immediate context. Revisit with knowledge graph (Phase 10). |
| Linked chunks as supplementary context, not citations | Correct | They weren't retrieved for the query — adding them to citations would be misleading. |
| Max 3 linked chunks | Good balance | 5 main candidates + 3 linked = 8 total context chunks, well within token limits. |
| First chunk (chunk_index=0) per linked note | Simple and effective | Opening context is most representative. Avoids another embedding query. |
| No LLM reranking for capture connections | Speed over precision | Raw hybrid scores are good enough for "here are related notes." Reranking would add 1-2s latency. |
| Capture never fails due to retrieval | Critical invariant | Entire retrieval block wrapped in try/except. Capture is the highest-priority user action. |
| Metadata summaries as snippets when available | Better UX | 1-2 sentence summaries are more useful than random 150-char chunk excerpts. Falls back gracefully. |

## Patterns Established

- **Link expansion after reranking, before synthesis:** This is the right injection point — reranking is expensive, link expansion is cheap (SQLite lookups). No need to rerank linked chunks.
- **Best-effort retrieval in non-retrieval endpoints:** The capture endpoint shows how to add retrieval to any endpoint without making it a hard dependency. The try/except pattern ensures the primary action always succeeds.
- **`Depends()` injection for retrieval components:** `LinkExpander` uses the same FastAPI dependency injection pattern as `HybridRetriever`, making it testable via `app.dependency_overrides`.

## Testing

- 32 new tests total (13 parser + 7 expander + 5 answerer + 7 capture connections)
- All 350 tests pass with lint, format, and type checks clean
- Manual QA: restart backend from project root, rebuild frontend, verify capture shows connection cards

## Future Considerations

- **Backlink following:** Notes that link *to* the retrieved note could also be valuable. Requires a separate backlink index.
- **Link extraction during indexing:** Storing links at index time would avoid runtime parsing. Worth it if link expansion becomes a latency bottleneck.
- **Clickable connection cards:** Currently informational only — no note viewer exists in the frontend. Adding one is a separate feature.
- **Connection persistence:** Connections are ephemeral. If users want to save/bookmark them, that's a separate feature.
