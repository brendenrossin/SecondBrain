# Capture Connection Surfacing — Show Related Notes After Quick Capture

> **Status:** Planned
> **Estimated effort:** 2-3 days
> **Depends on:** Phase 6.5 (quick capture), Phase 1-2 (hybrid retrieval)
> **Priority:** High — turns a fire-and-forget action into a knowledge moment

## Problem

When you capture a thought via Quick Capture, the system writes a file and says "Captured to Inbox/capture_*.md." That's it. You have no idea what's already in your vault that relates to what you just captured.

This is a missed opportunity. The moment of capture is when you're most engaged with the idea. Showing "you've thought about this before — here are related notes" would:
1. **Prevent duplication** — you see the existing note before the inbox processor creates a new one
2. **Surface forgotten context** — "oh right, I already have a note on this from 3 weeks ago"
3. **Build confidence** — you know the system is working because it immediately demonstrates awareness

The inbox processor does note matching during classification, but that happens asynchronously (next sync). By then, you've moved on.

## Solution

After writing the capture file, **perform a quick hybrid retrieval** using the captured text as a query. Return the top related notes in the API response. Show them in the frontend immediately after successful capture.

No LLM reranking — raw hybrid scores only, for speed. The goal is instant feedback (<500ms added latency), not perfect ranking.

### WI1: Backend — Add Connections to Capture Response

**Goal:** Optionally return related notes from the capture endpoint.

**Behavior:**
- After writing the capture file, use the `HybridRetriever` to search for the captured text
- Take the top 5 candidates (raw RRF score, no reranking)
- Deduplicate by note_path (multiple chunks from the same note → keep highest-scoring)
- Return as a new `connections` field in the response
- The retrieval is **conditional**: only run if the retriever is available (it won't be if the index is empty or hasn't been built yet)

**Files:**
- Modify `src/secondbrain/api/capture.py`
- Modify `src/secondbrain/models.py` — add `CaptureConnection` model, update `CaptureResponse`
- Modify `src/secondbrain/api/dependencies.py` — make retriever available to capture endpoint

**New model:**
```python
class CaptureConnection(BaseModel):
    """A note related to captured text."""
    note_path: str
    note_title: str
    snippet: str        # first 150 chars of the best-matching chunk
    score: float        # RRF score (0-1 range, higher = more relevant)

class CaptureResponse(BaseModel):
    """Response body for the /capture endpoint."""
    filename: str
    message: str
    connections: list[CaptureConnection]  # new field, defaults to []
```

**Algorithm:**
```python
# After writing the capture file:
connections = []
try:
    retriever = get_retriever()
    candidates = retriever.retrieve(request.text, top_k=10)

    # Deduplicate by note_path (keep highest RRF score per note)
    seen_paths: dict[str, RetrievalCandidate] = {}
    for c in candidates:
        if c.note_path not in seen_paths or c.rrf_score > seen_paths[c.note_path].rrf_score:
            seen_paths[c.note_path] = c

    # Take top 5 unique notes
    top_notes = sorted(seen_paths.values(), key=lambda c: c.rrf_score, reverse=True)[:5]

    connections = [
        CaptureConnection(
            note_path=c.note_path,
            note_title=c.note_title,
            snippet=c.chunk_text[:150].strip(),
            score=round(c.rrf_score, 4),
        )
        for c in top_notes
    ]
except Exception:
    # Retrieval failure should never block capture
    logger.debug("Connection surfacing failed, returning capture without connections")
```

**Key invariant:** Capture must never fail because of retrieval. The retrieval is best-effort. If it fails (empty index, DB locked, embedder not loaded), return the capture response with an empty connections list.

**Testing:**
- Capture with indexed vault → returns connections
- Capture with empty index → returns empty connections, capture succeeds
- Capture when retriever raises exception → returns empty connections, capture succeeds
- Connections are deduplicated by note_path
- Max 5 connections returned

---

### WI2: Backend — Metadata Enrichment (Optional, Low Cost)

**Goal:** If metadata is available for connected notes, include the summary instead of a raw chunk snippet.

**Behavior:**
- After finding connections via retrieval, check the metadata store for each connected note
- If a summary exists, use it as the snippet (more useful than a random chunk excerpt)
- If no metadata, fall back to the chunk text snippet

**Files:**
- Modify `src/secondbrain/api/capture.py` — add metadata lookup
- Modify `src/secondbrain/api/dependencies.py` — make metadata store available

**Design decision:** This is a nice-to-have within WI1. If the metadata store isn't available or the note doesn't have metadata, fall back gracefully. Never block on metadata.

**Testing:**
- Note with metadata → snippet is the summary
- Note without metadata → snippet is chunk text[:150]
- Metadata store unavailable → falls back to chunk text

---

### WI3: Frontend — Connection Cards

**Goal:** Show related notes in the capture UI after successful capture.

**Behavior:**
- After a successful capture that returns connections, display them below the success message
- Each connection is a compact card showing:
  - Note title (bold)
  - Snippet text (truncated, dimmed)
  - Folder badge (e.g., "10_Notes" or "30_Concepts")
- Cards are not clickable (no routing to notes in the current UI — we don't have a note viewer)
- Cards appear with a subtle fade-in animation
- Cards disappear when the user starts typing a new capture (or after 15 seconds)
- If no connections returned, show nothing extra (current behavior)

**Layout:**
```
┌─────────────────────────────────────┐
│ ✓ Captured to Inbox/capture_*.md    │
└─────────────────────────────────────┘

  Related in your vault:

  ┌─────────────────────────────────┐
  │ 10_Notes                        │
  │ Q3 Planning Notes               │
  │ Budget review scheduled for...  │
  └─────────────────────────────────┘
  ┌─────────────────────────────────┐
  │ 30_Concepts                     │
  │ Budget Allocation Framework     │
  │ The standard approach to...     │
  └─────────────────────────────────┘
```

**Files:**
- Modify `frontend/src/components/capture/CaptureForm.tsx` — add connection display
- Modify `frontend/src/lib/api.ts` — update `captureText()` return type to include connections

**Component structure:**
- No new component file needed — the connection list is simple enough to inline in `CaptureForm.tsx`
- Map over `connections` array from the API response
- Extract folder from `note_path` (first path segment before `/`)

**Testing:**
- Capture text that matches existing notes → connection cards appear
- Capture text with no matches → only success message shown
- Connection cards disappear when user starts new capture
- Mobile viewport: cards stack vertically, readable on small screens
- Connection cards show folder badge, title, and snippet

---

### WI4: API Response Contract Update

**Goal:** Ensure the frontend `api.ts` client handles the new response shape.

**Files:**
- Modify `frontend/src/lib/api.ts` — update `CaptureResponse` type and `captureText()` function

**Current type:**
```typescript
interface CaptureResponse {
  filename: string;
  message: string;
}
```

**New type:**
```typescript
interface CaptureConnection {
  note_path: string;
  note_title: string;
  snippet: string;
  score: number;
}

interface CaptureResponse {
  filename: string;
  message: string;
  connections: CaptureConnection[];
}
```

**Backward compatibility:** The backend always returns `connections` (empty array if no results). No conditional handling needed.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Synchronous retrieval at capture time | Yes | Retrieval takes <500ms (no reranking). The user is still looking at the screen. Async would require polling or websockets — over-engineered for this use case. |
| Skip LLM reranking | Yes | Reranking adds 1-2s and costs tokens. Raw hybrid scores are good enough for "here are related notes." This isn't answering a question — it's surfacing connections. |
| Deduplicate by note_path | Yes | Multiple chunks from the same note shouldn't show as separate connections. Keep the highest-scoring chunk's data per note. |
| Max 5 connections | Yes | More than 5 is noisy. 3-5 is the sweet spot for "useful at a glance." |
| Never block capture on retrieval failure | Critical | Capture is the highest-priority user action. If retrieval fails, the capture still succeeds with empty connections. |
| No clickable links to notes | For now | We don't have a note viewer in the frontend. Adding one is a separate feature. Connection cards are informational. |
| Use summary from metadata store when available | Yes | Metadata summaries are human-readable 1-2 sentence descriptions. Much better than a random 150-char chunk excerpt. Falls back gracefully. |
| Connections disappear on new input | Yes | Keeps the UI clean. The connections are for the *just-captured* text. Once you start a new thought, they're no longer relevant. |

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| LLM reranking of connections | Too slow and expensive for a capture feedback loop. Raw hybrid scores suffice. |
| "Link to existing note" action | Write-back feature (Phase 11). Showing connections is read-only. |
| "Append to existing note" from capture UI | The inbox processor handles routing. Adding a manual override from the capture page is a separate feature. |
| Push notifications for connections | No notification infrastructure exists. This is in-page feedback only. |
| Connection persistence (save/bookmark) | Over-engineering. Connections are ephemeral — useful in the moment, not stored. |
| Connections during inbox processing | The inbox processor already does note matching for routing. This feature is about *immediate* feedback at capture time, not classification. |

## Implementation Order

```
WI1: Backend capture + retrieval (core feature)
 │
 ├── WI2: Metadata enrichment (enhances WI1, can be done inline)
 │
 └── WI4: API type update (trivial, depends on WI1 response shape)
      │
      └── WI3: Frontend connection cards (depends on WI4 types)
```

WI1 + WI2 are backend-only and can be tested independently.
WI3 + WI4 are frontend and depend on the backend being complete.

## Testing

**Automated:**
- Capture endpoint with retriever: ~5 tests (connections returned, deduplicated, capped, fallback on error, empty index)
- Metadata enrichment: ~3 tests (summary available, no metadata, store unavailable)
- **Total: ~8 backend tests**

**Manual QA:**
- Capture a thought about a topic that has existing notes → verify 1-5 connection cards appear
- Capture a completely new topic → verify no connection cards (or low-relevance ones)
- Capture with an empty/unindexed vault → verify only success message, no errors
- Mobile (iPhone via Tailscale): verify connection cards are readable, not cramped
- Desktop: verify cards appear below success message with proper spacing
- Start typing a new capture → verify connection cards fade/disappear
- Verify capture latency: should be <1s total (write + retrieval)
- Verify the folder badge displays correctly (extracts first path segment)

## Files Modified

| File | Action |
|------|--------|
| `src/secondbrain/models.py` | Modify — add `CaptureConnection`, update `CaptureResponse` |
| `src/secondbrain/api/capture.py` | Modify — add retrieval + metadata lookup after file write |
| `src/secondbrain/api/dependencies.py` | Modify — expose retriever and metadata store to capture route |
| `frontend/src/lib/api.ts` | Modify — update `CaptureResponse` type |
| `frontend/src/components/capture/CaptureForm.tsx` | Modify — add connection card display |
| `tests/test_capture_connections.py` | Create — backend tests for connection surfacing |

## Important Notes

- **Embedder lazy-loading:** The first capture after a server restart will trigger the embedder to load (~2-3s for local model). Subsequent captures will be fast. This is acceptable — the embedder is already lazy-loaded for `/ask` queries.
- **Index freshness:** Connections are based on the current index. If you just captured 5 notes that haven't been indexed yet, they won't show as connections. This is expected and fine — the user understands the "next sync" model.
- **No reindex trigger:** Capture does not trigger reindexing. The daily sync handles that. This keeps capture fast and predictable.
