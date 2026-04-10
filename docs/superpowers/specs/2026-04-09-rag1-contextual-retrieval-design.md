# RAG-1: Contextual Retrieval — LLM-Generated Chunk Context Blurbs

> **Status:** Approved
> **Ticket:** RAG-1
> **Date:** 2026-04-09
> **Estimated effort:** 2-3 days

## Goal

At index time, use an LLM to generate short context blurbs for each chunk that situate it within its parent document. Prepend these blurbs before embedding and FTS5 indexing so both vector and keyword search benefit from document-level context.

## Motivation

Chunks lose document context after splitting. A chunk containing `"3 medium parsnips, peeled and chopped\n3/4 cup heavy cream"` has no indication it's from a Valentine's Day dinner recipe without its heading path. While heading paths help, they don't capture the full document topic or relationships between sections.

Based on [Anthropic's Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) technique, which showed a 67% reduction in retrieval failures when combined with hybrid search + reranking — exactly our existing pipeline.

### Progressive Disclosure for RAG

This feature implements the first layer of a progressive disclosure pattern applied to knowledge retrieval:

1. **RAG-1 (this ticket):** Chunk-level context blurbs — each chunk carries enough metadata for the retrieval system to assess relevance accurately
2. **RAG-3 (future):** Vault-level topic manifest — the LLM knows what's available before searching, deciding whether RAG is even needed

This mirrors how Claude Code's skill system works: load name + description first (manifest), fetch full content on demand (retrieval). Instead of raw chunks that require the model to infer context, each chunk carries a pre-computed summary of what it is and where it fits.

## Approach

**Inline ContextGenerator in the indexing pipeline.** New `ContextGenerator` class slots between chunking and embedding. Uses Anthropic Haiku directly (no prompt caching — vault is small enough that costs are negligible). Full document text sent with each chunk for maximum blurb quality.

Rejected alternatives:
- **Post-indexing enrichment pass** — Two-pass complexity, inconsistent state during gap, marginal benefit at current scale.
- **Blurbs at query time only** — Misses the biggest win: embeddings and BM25 don't capture document context. Defeats the core value.
- **Prompt caching** — Premature optimization at ~16 notes. Upgrade path when vault grows.

## Architecture

### New File: `src/secondbrain/indexing/context.py`

**`ContextGenerator`:**
- Constructor: takes Anthropic API key, model name (default `claude-haiku-4-5`), UsageStore for cost tracking
- Method: `generate_blurbs(note_title: str, note_content: str, chunks: list[Chunk]) -> list[str]`
  - For each chunk, calls Anthropic Haiku with full document + chunk
  - System prompt: context annotation assistant for a personal knowledge base
  - User prompt: full document text + specific chunk, asks for 1-2 sentence context blurb
  - Returns list of blurbs aligned 1:1 with input chunks
- On error (API failure, timeout): returns empty string for that chunk — indexing continues without context
- Logs each LLM call to UsageStore with `usage_type="context_generation"`
- Uses shared `trace_id` per file for grouping in admin traces tab

### Chunk Model Change: `src/secondbrain/models.py`

New field on `Chunk`:
```python
context_blurb: str | None = None
```

### Storage Changes

**Lexical store (`stores/lexical.py`):**
- New column on `chunks` table: `context_blurb TEXT` (nullable) via `ALTER TABLE`
- FTS5 virtual table must be recreated to include `context_blurb` — FTS5 column lists are fixed at creation. Migration: drop old FTS5 table, create new one with `context_blurb` column, rebuild from `chunks` content table. Existing `_rebuild_fts()` pattern handles the rebuild.

**Vector store (`stores/vector.py`):**
- Store `context_blurb` in ChromaDB metadata dict (schemaless, no migration needed)

### Embedder Change: `src/secondbrain/indexing/embedder.py`

Update `build_embedding_text()`:
```python
def build_embedding_text(chunk: Chunk) -> str:
    parts = []
    if chunk.context_blurb:
        parts.append(f"[Context: {chunk.context_blurb}]")
    if chunk.heading_path:
        parts.append(" > ".join(chunk.heading_path))
    parts.append(chunk.chunk_text)
    return "\n".join(parts)
```

Context blurb first (most important for embedding), then heading path, then chunk text.

### Indexing Pipeline Integration: `src/secondbrain/api/index.py`

Insert context generation between chunking and embedding in `_run_indexing()`:

```python
# After: chunks = chunker.chunk_note(note)
if context_generator:
    blurbs = context_generator.generate_blurbs(note.title, note.content, chunks)
    for chunk, blurb in zip(chunks, blurbs):
        chunk.context_blurb = blurb
# Before: text_for_embedding = build_embedding_text(chunk)
```

`ContextGenerator` is optional — `None` if no Anthropic API key or if disabled via config.

### Configuration: `src/secondbrain/config.py`

```python
context_generation_enabled: bool = True
```

Environment variable: `SECONDBRAIN_CONTEXT_GENERATION_ENABLED=false` to disable.

Context generation requires an Anthropic API key. If no key is configured, generation is silently skipped regardless of this setting.

## Example

**Raw chunk:**
```
3 medium parsnips, peeled and chopped
3/4 cup heavy cream
1/4 cup whole milk
```

**Generated context blurb:**
```
This chunk lists ingredients for the Parsnip Purée, part of a Valentine's Day Dinner recipe for Sesame Crusted Seared Ahi.
```

**Contextualized embedding text:**
```
[Context: This chunk lists ingredients for the Parsnip Purée, part of a Valentine's Day Dinner recipe for Sesame Crusted Seared Ahi.]
Recipes > Valentine's Day Dinner > Parsnip Purée
3 medium parsnips, peeled and chopped
3/4 cup heavy cream
1/4 cup whole milk
```

Now searching for "Valentine's Day dinner" matches this chunk via both BM25 (keyword match on "Valentine's Day") and vector search (semantic similarity to dinner recipe topic).

## Observability

**UsageStore:** Each context generation call logs with `usage_type="context_generation"`, provider, model, tokens, cost, latency, trace_id. Visible in the existing admin dashboard.

**OTel tracing:** Anthropic SDK calls are auto-instrumented by traceloop-sdk (TRACE-1). Context generation spans appear in `data/traces/*.jsonl` automatically.

**Cost estimate:** ~16 notes, ~50-100 chunks. Haiku pricing ($1/M input, $5/M output), ~500 tokens input + ~50 tokens output per chunk. Full re-index: ~$0.03-0.08. Negligible.

## Testing

**Unit tests:**
- `ContextGenerator.generate_blurbs()` returns correct number of blurbs aligned with chunks
- `ContextGenerator` returns empty strings on API error (graceful degradation)
- `build_embedding_text()` prepends blurb when present, omits when `None`
- `Chunk` model accepts `context_blurb` field
- Lexical store stores and retrieves `context_blurb`

**Integration tests:**
- Mock Anthropic client, run indexing pipeline end-to-end with context generation, verify blurbs in both stores
- Verify indexing works with `context_generation_enabled=False` (no blurbs, no errors)

No changes to existing retrieval/reranker/answerer tests — blurbs are baked into chunk content at index time.

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Haiku generates low-quality blurbs | Medium — wrong context hurts retrieval | Review sample blurbs after first re-index. Tune prompt if needed. |
| API errors during indexing | Low — chunks index without blurbs | Graceful degradation: empty string on error, log warning. |
| Cost growth with larger vault | Low — currently ~$0.05/re-index | Add prompt caching when vault exceeds ~100 notes. |
| Blurbs increase embedding text length | Low — ~50-100 extra tokens | Well within embedding model limits. May slightly shift similarity scores. |

## Not in Scope

- Prompt caching (add when vault grows)
- Topic manifest / vault-level summary (RAG-3)
- Re-ranking or answerer changes (they benefit passively from richer chunks)
- Frontend changes (no UI for context blurbs)
- Caching layer for blurbs (RAG-2 territory — incremental indexing handles this naturally)
