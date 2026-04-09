# RAG Quality & Performance (Phase 9.7)

## Motivation

The current RAG pipeline (hybrid BM25 + vector search → LLM reranking → answer synthesis) works well but has known limitations:

1. **Chunks lose document context** — A chunk saying "add parsnips, cream, simmer 15-20 minutes" has no indication it's from a Valentine's Day dinner recipe without its heading path. The heading path is prepended before embedding (good), but the full document context is not.
2. **No knowledge-base awareness** — The system always runs RAG on every query. There's no mechanism for the LLM to know what topics the vault covers, leading to irrelevant retrieval attempts on out-of-scope questions.
3. **Re-indexing recomputes everything** — Unchanged chunks still get re-embedded during full re-indexes. No caching layer exists.

## Components

### 1. Contextual Retrieval (Priority: High)

Based on [Anthropic's Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) technique.

**What it does:** At indexing time, for each chunk, send the full document + chunk to a cheap LLM to generate a short (50-100 token) context blurb. Prepend this blurb to the chunk before both embedding and BM25 indexing.

**Example:**
- Raw chunk: `"3 medium parsnips, peeled and chopped\n3/4 cup heavy cream\n1/4 cup whole milk"`
- Context blurb: `"This chunk lists ingredients for the Parsnip Purée, part of a Valentine's Day Dinner recipe for Sesame Crusted Seared Ahi."`
- Contextualized chunk: `"[Context: This chunk lists ingredients for the Parsnip Purée, part of a Valentine's Day Dinner recipe for Sesame Crusted Seared Ahi.]\n3 medium parsnips, peeled and chopped\n3/4 cup heavy cream\n1/4 cup whole milk"`

**Why it helps:**
- BM25 now matches on "Valentine's Day", "Sesame Ahi", "Parsnip Purée" even though those terms aren't in the raw chunk
- Vector embeddings capture the document-level topic, improving semantic matching
- Anthropic's published results: 67% reduction in retrieval failures when combined with hybrid search + reranking (which we already have)

**Implementation approach:**
- New `ContextGenerator` class that takes (full_document, chunk) and returns a context blurb
- Use Anthropic Haiku (cheapest) with prompt caching — the full document is the cached prefix, only the chunk-specific instruction varies per call. This reduces cost by ~90%.
- Store the context blurb alongside the chunk (new column in lexical store, stored in vector metadata)
- `build_embedding_text()` in `embedder.py` prepends the context blurb instead of (or in addition to) just the heading path
- Context blurbs are cached by `(document_hash, chunk_hash)` — only regenerated when content changes

**Cost estimate:** ~$0.01-0.05 per full vault re-index with prompt caching (Haiku pricing: $0.25/M input cached, $1.25/M output). Negligible for incremental re-indexing.

**Latency impact:** Indexing-time only. Query latency unchanged.

### 2. Topic Manifest / Knowledge-Base Summary (Priority: Medium)

**What it does:** Build a hierarchical summary of the vault's contents:
- **Chunk-level tags** — Already partially covered by heading paths and the contextual retrieval blurbs above
- **Document-level summary** — One-sentence summary per note (e.g., "Recipe Ideas: Contains Valentine's Day dinner recipes including Sesame Ahi, Parsnip Purée, and Buffalo Chicken Dip")
- **Vault-level manifest** — Aggregated summary of all documents: "Your knowledge base contains: personal recipes, daily work logs, project notes for SecondBrain and PwC projects, grocery lists, and restaurant recommendations."

**Why it helps:**
- The answerer can reference the vault manifest in its system prompt to confidently say "I don't have information about X in your notes"
- Enables future tool-use pattern: the LLM decides whether to call RAG based on the manifest, rather than always running retrieval
- Document summaries can improve search — embed the summary alongside chunks for better semantic coverage

**Implementation approach:**
- Generate document summaries during indexing (Haiku, same prompt caching pattern as contextual retrieval)
- Store in a new `document_summaries` table in the metadata store
- Aggregate into a vault manifest (regenerated periodically or on significant vault changes)
- Inject vault manifest into answerer system prompt (small token cost, big context benefit)

### 3. Caching Layer (Priority: Low-Medium)

**Embedding cache:**
- SQLite table: `content_hash → embedding_vector`
- Check before computing during re-indexing
- Highest value for full re-indexes; incremental re-indexing already skips unchanged chunks via checksum

**Context blurb cache (for contextual retrieval):**
- SQLite table: `(document_hash, chunk_hash) → context_blurb`
- Only regenerate when document or chunk content changes
- Critical for cost control — without this, every re-index re-generates all blurbs

**Reranker result cache:**
- TTL-based (1-24 hours) cache of `(query_hash, chunk_id_set) → reranked_scores`
- Moderate value — helps with repeated/similar queries (morning briefing, common questions)
- Simple LRU with expiration

## What's Already Working Well

These parts of the pipeline should be preserved as-is:

- **Heading-aware chunking** with recursive separator strategy (700 chars target, 100 overlap)
- **Stable chunk IDs** via SHA1 hash for incremental indexing
- **Hybrid search** with RRF merging (k_vec=30, k_lex=50, rrf_k=60)
- **LLM reranking** with 0-10 scoring, hallucination detection, retrieval labels
- **Wiki link expansion** following `[[links]]` one hop for connected context
- **Conversation history** in answer synthesis (last 10 messages)

## Implementation Order

1. Contextual retrieval (highest impact, pairs with existing hybrid search)
2. Topic manifest / vault summary (enables smarter RAG invocation)
3. Caching layer (performance optimization, do alongside or after #1)

## Open Questions

- Should contextual retrieval use Anthropic prompt caching or local Ollama? Prompt caching is cheaper but requires API. Local is free but much slower at indexing time.
- How frequently should the vault manifest be regenerated? On every sync? Daily? Only on significant changes?
- Should document summaries be embedded as separate vectors (multi-representation indexing) or just used for the manifest?
