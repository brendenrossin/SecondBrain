# Engineering Review — System Health & Improvement Priorities

**Date:** 2026-02-07
**Scope:** Full codebase review of backend, frontend, indexing, retrieval, ingestion, and eval systems
**Purpose:** Establish review criteria for ongoing changes, identify high-leverage improvement areas, and document known gaps

---

## 1. Non-Negotiable Principles

Any change that violates these gets rejected. These are derived from the PRD, ROADMAP decisions log, and architectural constraints established across Phases 0–4.

| Principle | What It Means in Practice |
|-----------|--------------------------|
| **Vault is source of truth** | No application state outside Obsidian files and their derived indexes. No database should contain information that can't be regenerated from the vault. |
| **Suggestion-only** | The system recommends, never acts autonomously on the vault. No auto-editing, no auto-tagging, no silent writes. |
| **Local-first** | Cloud services (OpenAI, hosted embeddings) are opt-in toggles, not requirements. The system must function fully with local Ollama + BAAI/bge-base-en-v1.5. |
| **Simple over clever** | If a batch job does the job, don't build an agent framework. If a better prompt fixes it, don't add a new service. Minimum viable complexity for the current need. |
| **Incremental, test-driven delivery** | Every feature ships with tests. Test count has progressed 90 → 122 → 156. Regressions are unacceptable. |

---

## 2. Current System Assessment

### What's Working Well

- **Hybrid retrieval (BM25 + vectors + RRF)** — solid foundation, measurable improvement from embedding upgrade (Recall@5: 0.710 → 0.783)
- **LLM reranker with hallucination detection** — the `HALLUCINATION_RISK` label (high vector similarity + low rerank score) catches a specific, dangerous failure mode
- **Incremental indexing** — mtime pre-filter + SHA-1 content hash avoids unnecessary re-embedding
- **Bi-directional task sync** — daily notes ↔ aggregate files, with add-only due date sync (safe direction)
- **Trigger-file architecture** — avoids all ChromaDB single-process concurrency bugs
- **Aggressive roadmap pruning** — task lifecycle engine, contradiction detection, drift detection, and push notifications were all correctly cut

### What Needs Improvement

These are the areas where changes would have the highest impact on RAG accuracy and system quality, ordered by leverage.

#### Priority 1: Inbox Ingestion Quality (Highest Leverage)

**Current state:** Single LLM call per inbox file, no validation of output, no duplicate detection, destructive delete of source file.

**Problems:**
- If the LLM misclassifies a note or generates bad JSON, the original file is deleted — data loss with no recovery path
- No schema validation on the LLM's structured output (trusts blindly)
- No duplicate detection — same dictated note dropped twice creates two entries
- The `_append_under_heading()` function uses string splitting and line counting — fragile against unusual formatting
- Focus vs. task classification relies entirely on prompt engineering with no guardrails

**Why this is highest leverage:** Garbage in, garbage out. Poorly structured notes → poor chunks → poor embeddings → poor retrieval. Fixing ingestion quality improves everything downstream.

**Approved improvement directions:**
- Validate LLM structured output against a schema before acting on it
- Add duplicate detection (content hash comparison against recent notes)
- Preserve original file until routing is confirmed successful (move to archive, not delete)
- Improve section templates in daily notes to be more consistent for downstream parsing
- Better error handling with retry logic for malformed LLM responses

**Not approved:**
- Multi-agent pipelines (one to "understand", one to "route") — a better prompt + validation is simpler and sufficient
- LangChain/CrewAI/agent frameworks — unnecessary abstraction for a single classification task
- Building a separate ingestion database or queue system

#### Priority 2: Vault Connector & Indexing Hygiene

**Current state:** Indexes everything including `Inbox/` (raw unprocessed notes) and auto-generated files (`Tasks/All Tasks.md`, `Tasks/Completed Tasks.md`).

**Problems:**
- Raw inbox files get indexed before the inbox processor routes them — dilutes search quality with unstructured dictation dumps
- Auto-generated task aggregation files are indexed alongside authored content — search results mix generated summaries with original notes
- No special handling for Obsidian-specific syntax: `[[wikilinks]]`, `![[embeds]]`, `%%comments%%`, callouts, dataview queries — these pass through as raw text noise

**Approved improvement directions:**
- Exclude `Inbox/` from indexing (raw notes shouldn't be searchable until processed)
- Consider excluding or tagging auto-generated files (`Tasks/*.md`) so retrieval can distinguish authored vs. generated content
- Parse `[[wikilinks]]` as structured metadata (explicit links) rather than embedding the bracket syntax
- Strip or handle `%%comments%%` and other Obsidian-only syntax before chunking

**Not approved:**
- Removing `Tasks/*.md` from the index entirely (they appear in eval expected results and are legitimately useful for task queries)
- Complex Obsidian plugin integration or sync protocols

#### Priority 3: Chunker Quality

**Current state:** 700-character target, character-based splitting, 100-character overlap. Markdown-aware heading boundaries but no awareness of code blocks, tables, or Obsidian syntax.

**Problems:**
- Character-based sizing doesn't align with token limits — may under-utilize or over-utilize embedding model context windows
- Code blocks and Markdown tables can be split mid-structure, producing nonsensical chunks
- 700 characters is relatively small (~100-150 tokens) — a single concept spread across 2-3 paragraphs may get split
- The `chunk_index` in the chunk ID means inserting content before existing chunks cascades new IDs, triggering unnecessary re-embedding
- Sentence-ending split on `. ` may mis-handle abbreviations ("Dr. Smith")

**Approved improvement directions:**
- Preserve code blocks and tables as atomic units (don't split mid-structure)
- Consider token-aware sizing that respects the embedding model's context window
- Evaluate whether larger chunk sizes (1000-1500 chars) improve retrieval for the specific vault content
- Remove `chunk_index` from chunk ID hash if feasible (use content-only hashing for better stability)

**Not approved:**
- Switching to a third-party chunking library (the current recursive splitter is well-designed for the use case)
- Implementing full AST-based Markdown parsing (overkill for personal notes)

#### Priority 4: Eval Framework Gaps

**Current state:** 23 test queries, note-level deduplication, measures only HybridRetriever (not reranker or synthesis). No automated regression checks.

**Problems:**
- Note-level dedup inflates recall — if a wrong chunk from the right note appears first, the note is counted as a "hit"
- Reranker is not evaluated — we can't measure whether LLM reranking actually improves results
- No per-tag metric breakdowns — can't identify which query categories (semantic, keyword, temporal) are weak
- Static ground truth references specific dated files — will go stale as the vault grows
- No automated regression check — baselines are only compared manually via JSON reports

**Approved improvement directions:**
- Add chunk-level eval metrics alongside note-level (more granular quality signal)
- Add reranker evaluation (measure Recall/Precision/MRR after reranking, not just after retrieval)
- Add per-tag aggregation in reports (e.g., "semantic queries average 0.6 Recall@5, keyword queries average 0.9")
- Add more test queries as the vault grows, especially for edge cases
- Consider a simple regression check (compare against last saved baseline, warn if metrics drop)

**Not approved:**
- RAGAS or LangChain eval dependencies (the current pure Python + YAML approach is deliberately dependency-free)
- LLM-as-judge for answer quality (adds cost and non-determinism for unclear benefit at this scale)

#### Priority 5: Contextualized Embeddings

**Current state:** Spec'd in INDEXING_PIPELINE.md as "recommended" but not implemented.

**What it is:** Before embedding a chunk, an LLM generates a one-sentence context prefix based on the document title, frontmatter, and surrounding chunks. This helps disambiguate chunks that contain pronouns or vague references ("it", "this system", "the same approach").

**Trade-off:** Cost is 1 LLM call per chunk at index time. For a vault of ~50-100 notes producing ~500 chunks, this is manageable. For a vault of 10,000 notes, it becomes expensive.

**Assessment:** Worth implementing once ingestion quality and chunking are improved (Priorities 1-3). Implementing it before fixing the input quality would be polishing a noisy signal.

#### Priority 6: Query Transformation

**Current state:** No pronoun resolution, no conversation context injection, no query expansion.

**Impact:** Queries like "what about that thing I mentioned?" or "tell me more about the same topic" fail completely. For a personal memory system used conversationally, this is a meaningful gap.

**Assessment:** Explicitly deferred in the indexing pipeline spec. Worth revisiting after Priorities 1-4, but not urgent — the chat UI can work around this with explicit queries.

---

## 3. Review Criteria for Incoming Changes

### Approve Quickly

- Inbox processor improvements: validation, duplicate detection, error handling, safer file operations
- Vault connector excluding `Inbox/` from indexing
- Wikilink-aware parsing (extracting `[[links]]` as metadata)
- Expanding the eval harness (more queries, per-tag breakdowns, reranker coverage)
- Better heading/section structure in daily notes for chunk quality
- Bug fixes with tests

### Require Justification

- New dependencies (must demonstrate clear value over what exists)
- Changes to the retrieval algorithm (RRF weights, reranking thresholds) — must be backed by eval results
- New API endpoints — must serve a clear user-facing need
- Schema changes to existing stores — must be backwards-compatible or include migration

### Push Back / Reject

- **New databases or stores** — SQLite + ChromaDB is sufficient at this scale
- **Agent frameworks or multi-step LLM pipelines** — a better prompt + validation is the right fix
- **Complex state machines** — task lifecycle was already cut for good reasons (source-of-truth conflict)
- **Changing the retrieval algorithm before improving input quality** — fix the data first, tune the algorithm second
- **Any write-back to vault** without the changeset/PR workflow from Phase 8
- **Over-abstraction** — helpers, utilities, or abstractions for one-time operations
- **Feature flags or backwards-compatibility shims** when direct changes are simpler

---

## 4. Known Documentation Inconsistencies

These should be resolved but are not blocking:

| Issue | Location | Resolution |
|-------|----------|------------|
| Chunk ID hash algorithm | DATA_MODEL.md says sha256; INDEXING_PIPELINE.md says sha1; implementation uses sha1 | Update DATA_MODEL.md to match implementation (sha1) |
| Chunk ID input fields | DATA_MODEL.md includes `note_id`; INDEXING_PIPELINE.md includes `note_path` + `chunk_index` | Reconcile to match actual `chunker.py` implementation |
| `vault_id` concept | Referenced in DATA_MODEL.md note_id formula but never defined or used anywhere | Remove from DATA_MODEL.md or define if needed |
| Gradio UI references | PRD.md still has full Gradio UI spec section | Update PRD to reference Next.js frontend |
| Default embedding model | Code defaults to `all-MiniLM-L6-v2`; CLAUDE.md/config docs say `BAAI/bge-base-en-v1.5` | Align — BGE is the intended default per Phase 2 upgrade |
| Reranker chunk truncation | Reranker truncates chunks to 500 characters in the scoring prompt | Not documented; add to INDEXING_PIPELINE.md |
| Eval excludes reranker | Eval harness only tests HybridRetriever, not the full pipeline | Document this limitation in eval section |

---

## 5. Improvement Sequencing

The recommended order for changes, based on leverage and dependency:

```
1. Inbox ingestion quality     (highest leverage — fixes input quality)
   ↓
2. Vault connector hygiene     (exclude raw/generated files from index)
   ↓
3. Chunker improvements        (better chunks from better-structured notes)
   ↓
4. Eval framework expansion    (measure the impact of 1-3)
   ↓
5. Contextualized embeddings   (polish the signal, now that input is clean)
   ↓
6. Query transformation        (improve conversational query handling)
```

Each step should include eval runs before and after to measure impact. Do not skip to step 5 or 6 without completing 1-3 — improving embeddings on noisy input is wasted effort.
