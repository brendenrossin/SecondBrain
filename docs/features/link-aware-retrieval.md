# Link-Aware Retrieval — 1-Hop Wiki Link Following in RAG

> **Status:** Planned
> **Estimated effort:** 2-3 days
> **Depends on:** Phase 2 (hybrid retrieval), Phase 3 (metadata extraction)
> **Priority:** High — makes retrieval smarter with no new infrastructure

## Problem

When the RAG pipeline retrieves chunks, it only finds chunks that are **semantically or lexically similar** to the query. It completely ignores the explicit `[[wiki links]]` the user created to connect related ideas.

Example: a query about "Project Alpha timeline" retrieves a chunk containing `[[Q3 Planning Notes]]` and `[[Sarah 1:1 2026-01-15]]`. Those linked notes contain critical context (the planning constraints, the conversation where deadlines were discussed) — but they won't surface because they aren't semantically similar to "Project Alpha timeline."

The vault's link structure is a curated knowledge graph that the user built manually. Ignoring it means we're leaving the highest-signal relationships on the table.

## Solution

After the reranker scores the top candidates, **parse `[[wiki links]]` from retrieved chunks**, resolve them to note paths, fetch a representative chunk from each linked note, and inject them as **supplementary context** for the answerer. One hop only. No Neo4j needed.

### WI1: Wiki Link Parser Utility

**Goal:** Extract `[[wiki links]]` from markdown text.

**Behavior:**
- Parse standard Obsidian wiki links: `[[Note Title]]`, `[[Note Title|display text]]`, `[[Note Title#heading]]`
- Return the **target title** (strip aliases, headings, block refs)
- Deduplicate: if the same note is linked twice in a chunk, return it once
- Ignore links inside code blocks (`` ` `` and `` ``` ``)

**Files:**
- Create `src/secondbrain/vault/links.py`

**Key detail:** The regex pattern is `\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]` — capture group 1 is the target title.

**Testing:**
- `[[Simple Note]]` → `"Simple Note"`
- `[[Note Title|alias]]` → `"Note Title"`
- `[[Note Title#heading]]` → `"Note Title"`
- `[[Note Title#heading|alias]]` → `"Note Title"`
- `[[Note]]` inside `` `code` `` → excluded
- Multiple links in one chunk → deduplicated list
- No links → empty list

---

### WI2: Link Resolver (Title → Note Path Lookup)

**Goal:** Resolve a wiki link title to a `note_path` in the indexed vault.

**Behavior:**
- Query the `chunks` table in LexicalStore: `SELECT DISTINCT note_path, note_title FROM chunks WHERE LOWER(note_title) = LOWER(?)`
- Return the first match (Obsidian titles are unique within a vault)
- If no match, return `None` (the linked note might not be indexed, or might be in an excluded folder)

**Files:**
- Add `resolve_note_path(title: str) -> str | None` method to `LexicalStore` (`src/secondbrain/stores/lexical.py`)

**Design decision:** Use LexicalStore for resolution (not the metadata store) because it has every indexed note's title and is already available in the retrieval pipeline via `HybridRetriever`.

**Testing:**
- Exact title match → returns note_path
- Case-insensitive match → returns note_path
- No match → returns `None`
- Multiple chunks from same note → returns single note_path

---

### WI3: Linked Context Fetcher

**Goal:** Given a list of note paths from wiki links, fetch one representative chunk per note to use as supplementary context.

**Behavior:**
- For each linked note_path, fetch all chunks from the LexicalStore: `SELECT * FROM chunks WHERE note_path = ? ORDER BY chunk_index`
- Select the **first chunk** (chunk_index=0) as the representative — it typically contains the note's opening context, which is the most useful for orientation
- Skip notes that are already in the reranked candidate set (deduplication)
- Cap at **3 linked chunks total** across all retrieved candidates (prevent context bloat)
- If more than 3 links are found across all candidates, prefer links from higher-scoring candidates

**Files:**
- Create `src/secondbrain/retrieval/link_expander.py`

**Interface:**
```python
class LinkExpander:
    def __init__(self, lexical_store: LexicalStore) -> None: ...

    def expand(
        self,
        ranked_candidates: list[RankedCandidate],
        max_linked: int = 3,
    ) -> list[LinkedContext]:
        """Parse wiki links from top candidates and fetch linked chunks."""
        ...

@dataclass
class LinkedContext:
    note_path: str
    note_title: str
    chunk_text: str
    linked_from: str  # note_title of the source that contained the [[link]]
```

**Algorithm:**
1. For each ranked candidate (in score order):
   a. Parse `[[wiki links]]` from `candidate.chunk_text`
   b. Resolve each title → note_path via LexicalStore
   c. Skip if note_path is already in candidates or already collected
   d. Fetch first chunk from that note
   e. Add to results until `max_linked` reached
2. Return collected `LinkedContext` list

**Testing:**
- Candidate with `[[Note A]]` and `[[Note B]]` → fetches both
- Candidate links to note already in reranked set → skipped
- More than 3 links across candidates → capped at 3
- Unresolvable link → skipped silently
- No links in any candidate → returns empty list

---

### WI4: Answerer Context Integration

**Goal:** Inject linked context into the answerer's context window alongside reranked candidates.

**Behavior:**
- In `Answerer._build_context()`, after the main candidate context, append a clearly labeled **"Connected Notes"** section
- Format each linked chunk similarly to candidates but with a different header:
  ```
  ---

  CONNECTED NOTES (linked from retrieved results):

  [C1] [10_Notes] Connected Note Title (linked from: Source Note Title)
  chunk text here...
  ```
- Update the system prompt to mention connected notes: "You also have access to connected notes that are explicitly linked from the retrieved sources. Use them for additional context."

**Files:**
- Modify `src/secondbrain/synthesis/answerer.py` — `_build_context()` method
- Modify `src/secondbrain/synthesis/answerer.py` — `SYSTEM_PROMPT`

**Design decision:** Connected notes are labeled differently from primary candidates so the LLM understands they weren't directly retrieved for the query — they're supplementary context from the note graph. This prevents the LLM from over-weighting them.

**Testing:**
- Context with 3 candidates + 2 linked notes → properly formatted with sections
- Context with 0 linked notes → no "CONNECTED NOTES" section appended
- System prompt includes connected notes instruction

---

### WI5: Pipeline Integration

**Goal:** Wire the link expander into the `/ask` and `/ask/stream` endpoints.

**Behavior:**
- After reranking, call `LinkExpander.expand(ranked_candidates)` to get linked context
- Pass the linked context to `Answerer.answer()` and `Answerer.answer_stream()` (new optional parameter)
- No changes to citations — linked notes are context, not citations (they weren't retrieved for the query)

**Files:**
- Modify `src/secondbrain/api/ask.py` — both `ask()` and `ask_stream()` functions
- Modify `src/secondbrain/api/dependencies.py` — add `get_link_expander()` dependency
- Modify `src/secondbrain/synthesis/answerer.py` — `answer()` and `answer_stream()` signatures

**Testing:**
- Full integration test: query that matches a note with wiki links → answer incorporates linked context
- Query with no links in results → behaves identically to current pipeline
- Latency: link expansion adds 1-2 SQLite queries, should be <10ms

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where to inject linked context | After reranking, before synthesis | Reranking is the expensive step. Link expansion is cheap (SQLite lookups). No need to rerank linked chunks — they're supplementary. |
| Max linked chunks | 3 | Prevents context window bloat. With 5 main candidates + 3 linked = 8 context chunks, well within token limits. |
| Which chunk to pick per linked note | First chunk (chunk_index=0) | Opening context is most representative. Avoids embedding another query to find the "best" chunk — keeps it simple. |
| Linked chunks as citations? | No — supplementary context only | They weren't retrieved for the query. Adding them as citations would be misleading. The LLM can reference them in its answer, but they don't appear in the citation list. |
| Resolution via LexicalStore | Yes (not metadata store) | LexicalStore is already in the retrieval pipeline, has note_title indexed, and is the simplest path. No new dependencies. |
| Code block exclusion | Strip links inside backticks | Prevents treating code examples or template references as real links. |

## What's Explicitly Out of Scope

| Excluded | Rationale |
|----------|-----------|
| Multi-hop traversal (2+ hops) | Complexity explosion. One hop covers the immediate context. Revisit with knowledge graph (Phase 10). |
| Backlink following (notes that link *to* the retrieved note) | Requires a separate backlink index. Worth exploring later but doubles the scope. |
| Link extraction during indexing (stored in DB) | Would be faster at query time but requires schema changes and reindexing. Start with runtime parsing — optimize later if needed. |
| Reranking linked chunks | Over-engineering. They're already curated by the user (they chose to link them). Trust the user's signal. |
| Surfacing linked notes in the frontend | No UI changes needed. The LLM uses linked context invisibly to produce better answers. If we want to show "also used context from: X, Y" in the UI, that's a separate feature. |

## Implementation Order

```
WI1: Wiki link parser
 │
 ├── WI2: Link resolver (depends on WI1 for titles)
 │    │
 │    └── WI3: Linked context fetcher (depends on WI2 for resolution)
 │              │
 │              ├── WI4: Answerer integration (depends on WI3 for linked context)
 │              │
 │              └── WI5: Pipeline wiring (depends on WI3 + WI4)
 │
 WI1 and WI2 can be developed in parallel since WI2 is a LexicalStore method.
 WI4 and WI5 depend on WI3.
```

## Testing

**Automated:**
- Wiki link parser: ~10 tests (standard links, aliases, headings, code blocks, edge cases)
- Link resolver: ~4 tests (exact match, case-insensitive, no match, dedup)
- Link expander: ~6 tests (expansion, dedup with candidates, cap, no links, unresolvable)
- Answerer context: ~3 tests (with linked context, without, prompt includes instruction)
- Integration: ~2 tests (end-to-end with mock data)
- **Total: ~25 tests**

**Manual QA:**
- Ask a question about a topic where notes contain wiki links to related notes
- Verify the answer incorporates information from linked notes
- Ask a question where no retrieved chunks contain wiki links → verify behavior is unchanged
- Check latency: link expansion should add <50ms to total response time
- Verify linked context doesn't appear in the citation list

## Files Modified

| File | Action |
|------|--------|
| `src/secondbrain/vault/links.py` | Create — wiki link parser |
| `src/secondbrain/stores/lexical.py` | Modify — add `resolve_note_path()` |
| `src/secondbrain/retrieval/link_expander.py` | Create — linked context fetcher |
| `src/secondbrain/synthesis/answerer.py` | Modify — `_build_context()`, `SYSTEM_PROMPT`, method signatures |
| `src/secondbrain/api/ask.py` | Modify — wire link expander into both endpoints |
| `src/secondbrain/api/dependencies.py` | Modify — add `get_link_expander()` |
| `tests/test_links.py` | Create — parser tests |
| `tests/test_link_expander.py` | Create — expander tests |
| `tests/test_answerer_links.py` | Create — answerer integration tests |
