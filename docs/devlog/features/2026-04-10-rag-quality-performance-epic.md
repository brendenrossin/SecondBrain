# Feature: RAG Quality & Performance Epic (RAG-1, RAG-2, RAG-3)

**Date:** 2026-04-10
**PRs:** [#5](https://github.com/brendenrossin/SecondBrain/pull/5), [#6](https://github.com/brendenrossin/SecondBrain/pull/6)

## Summary

Completed the full RAG Quality & Performance epic across three tickets: contextual retrieval (RAG-1), caching layer (RAG-2), and vault manifest (RAG-3). Together these improve retrieval accuracy by adding LLM-generated context to chunks, reduce reindex time by skipping unchanged content, and give the answerer vault-level awareness.

## Problem / Motivation

The RAG pipeline treated each chunk in isolation — no document-level context, no awareness of what the vault contained overall, and full reindexes were expensive because every chunk was re-embedded even if unchanged. This hurt answer quality (chunks lacked context about their source note) and made iteration slow.

## Solution

### RAG-1: Contextual Retrieval
- Added `ContextGenerator` that calls Anthropic Haiku to produce a 2-3 sentence context blurb for each chunk at index time
- Context blurb is prepended to the embedding text (improving vector similarity) and stored alongside the chunk in both vector and lexical stores
- Progressive disclosure: blurbs are available to the reranker and answerer as additional context

### RAG-2: Caching Layer (IndexCache)
- SQLite-based `IndexCache` that tracks content hashes per chunk
- On reindex, compares current chunk hash against cached hash — skips embedding generation and store writes for unchanged chunks
- Dramatically reduces reindex time for incremental vault changes

### RAG-3: Vault Manifest (ManifestGenerator)
- `ManifestGenerator` produces a structured summary of the vault's contents (note titles, categories, topic clusters)
- Manifest is passed to the `Answerer` as `vault_manifest` parameter, giving the LLM awareness of what the knowledge base contains
- Enables better scoping of answers ("based on your vault...") and honest "I don't have information on X" responses

## Files Modified

**RAG-1 (Contextual Retrieval):**
- `src/secondbrain/indexing/context.py` — ContextGenerator class
- `src/secondbrain/models.py` — context_blurb field on Chunk
- `src/secondbrain/config.py` — context_generation_enabled setting
- `src/secondbrain/stores/lexical.py` — context_blurb column
- `src/secondbrain/stores/vectors.py` — context_blurb in metadata
- `src/secondbrain/indexing/embedder.py` — prepend blurb to embedding text

**RAG-2 (Caching Layer):**
- `src/secondbrain/stores/index_cache.py` — IndexCache (new)
- `src/secondbrain/api/dependencies.py` — cache wiring
- `src/secondbrain/api/index.py` — skip-unchanged logic
- `tests/test_index_cache.py` — comprehensive tests

**RAG-3 (Vault Manifest):**
- `src/secondbrain/indexing/manifest.py` — ManifestGenerator (new)
- `src/secondbrain/synthesis/answerer.py` — vault_manifest parameter
- `src/secondbrain/api/dependencies.py` — manifest wiring

## Key Decisions & Trade-offs

- **Haiku for context blurbs:** Chose Anthropic Haiku over GPT-4o-mini for context generation — fast, cheap, good enough for 2-3 sentence summaries. Cost is ~$0.01 per full reindex at current vault size.
- **SQLite for IndexCache (not in-memory):** Persists across server restarts. Uses WAL mode consistent with other SQLite stores. Content hash comparison is O(1) per chunk.
- **Manifest is regenerated on full reindex, not incrementally:** Simpler implementation. At current vault size (~16 notes), regeneration is instant. May need incremental updates at 1000+ notes.
- **RAG-2 and RAG-3 bundled in one PR:** They were independent but small enough to review together. User preference for bigger batches over many small PRs.

## Patterns Established

- **IndexCache pattern:** Hash-based skip logic for any expensive per-chunk operation. Future caches (e.g., reranker result cache) can follow the same SQLite + content_hash approach.
- **ManifestGenerator pattern:** Vault-level metadata generated at index time and injected into LLM prompts. Sets precedent for other index-time metadata (e.g., entity indexes, topic clusters).
- **Context blurb prepending:** Embedding text = context_blurb + original chunk. This pattern can be extended with other metadata (tags, dates) if needed.

## Testing

- `tests/test_index_cache.py` — 233 lines covering cache hits/misses, schema init, hash comparison, full rebuild bypass
- RAG-1 tested via existing retrieval integration tests (context blurbs improve result relevance)
- Full reindex run post-merge to verify all three features work end-to-end

## Future Considerations

- **Manifest scaling:** At large vault sizes, manifest may exceed LLM context limits. Will need summarization or top-N topic selection.
- **Cache invalidation:** Currently only content-hash based. If embedding model changes, cache should be invalidated (manual full_rebuild=true for now).
- **Reranker cache:** Natural next step — cache reranker scores for query+chunk pairs. Would further reduce latency for repeated queries.
