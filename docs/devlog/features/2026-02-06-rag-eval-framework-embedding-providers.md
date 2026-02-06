# Feature: RAG Eval Framework + Multi-Provider Embeddings

**Date:** 2026-02-06
**Branch:** main

## Summary

Added a zero-dependency RAG evaluation harness for measuring retrieval quality against ground truth queries, and refactored the embedding system to support multiple providers (local sentence-transformers and OpenAI API). This enables data-driven comparison of embedding models to fix known semantic retrieval gaps.

## Problem / Motivation

The RAG pipeline uses `all-MiniLM-L6-v2` (384-dim), a small/fast but low-accuracy embedding model. Concrete failure: asking "who do I still need to reach out or respond to?" missed the "Update resume and send to Griffin from Snowflake" task entirely. The system couldn't bridge the semantic gap between "reach out" and "send resume to." There was no way to measure retrieval quality or compare alternative models.

## Solution

**Phase 1 — Eval Framework:** A simple YAML-driven eval harness that runs queries against the hybrid retriever and computes Recall@K, Precision@K, and MRR. Results are printed as a human-readable table and saved as JSON to `data/eval/` for comparison across model configurations. 23 ground truth queries covering 7 categories: core retrieval, work task chains, personal/life admin, project context, semantic gaps, and concept notes.

**Phase 2 — Multi-Provider Embeddings:** Introduced an `EmbeddingProvider` protocol with two implementations: `SentenceTransformerProvider` (local, supports BGE query prefixes) and `OpenAIEmbeddingProvider` (API, supports configurable dimensions). The existing `Embedder` class wraps the provider for backwards compatibility. Vector store now tracks which embedding model was used for indexing and warns on mismatch.

## Files Modified

**New (eval framework):**
- `src/secondbrain/eval/__init__.py` — package init
- `src/secondbrain/eval/metrics.py` — Recall@K, Precision@K, MRR functions
- `src/secondbrain/eval/eval_harness.py` — RAGEvaluator, report printing/saving
- `src/secondbrain/eval/eval_queries.yaml` — 23 ground truth queries
- `src/secondbrain/eval/__main__.py` — CLI entry point

**Modified (embedding providers):**
- `src/secondbrain/indexing/embedder.py` — EmbeddingProvider protocol, SentenceTransformerProvider, OpenAIEmbeddingProvider, backwards-compatible Embedder wrapper
- `src/secondbrain/config.py` — `embedding_provider`, `openai_embedding_model`, `openai_embedding_dimensions` settings
- `src/secondbrain/stores/vector.py` — model metadata storage + mismatch detection
- `src/secondbrain/api/dependencies.py` — provider factory based on config
- `src/secondbrain/api/index.py` — stores model name after indexing

**Infrastructure:**
- `Makefile` — added `eval` target
- `pyproject.toml` — added `pyyaml` dependency, `types-PyYAML` dev dependency

## Key Decisions & Trade-offs

- **No RAGAS/LangChain dependency:** The eval harness is pure Python + YAML. Retrieval-only metrics (no LLM answer eval) keep it fast and deterministic. Answer quality eval can be added later.
- **Protocol-based providers:** Used a `Protocol` class instead of ABC so that both providers remain plain classes without inheritance overhead. `runtime_checkable` enables isinstance checks if needed.
- **Backwards-compatible Embedder wrapper:** All existing code using `Embedder.embed()` and `embed_single()` continues to work unchanged. `embed_single()` now delegates to `embed_query()` which handles BGE query prefixes automatically.
- **Note-level deduplication in eval:** Retrieval returns chunks, but eval compares at the note level. `_dedupe_note_paths()` preserves rank order while deduplicating.
- **Model metadata in ChromaDB:** Stored as collection metadata via `modify()`. If metadata is missing (old collections), no mismatch is reported — avoids false alarms on first upgrade.

## Patterns Established

- **Eval queries in YAML with tags:** Tags like `[semantic, work, chain]` allow filtering results by category. New queries should follow this convention.
- **`embed()` for documents, `embed_query()` for queries:** This distinction matters for BGE-family models that use query prefixes. All query-time embedding should use `embed_query()`.
- **Provider selection via config:** `SECONDBRAIN_EMBEDDING_PROVIDER=openai` switches providers. New providers (e.g., Cohere, local Ollama embeddings) should implement the `EmbeddingProvider` protocol.

## Testing

- All 122 existing tests pass with no changes
- Zero ruff lint errors across the full codebase
- No new mypy errors (all remaining are pre-existing chromadb/openai type issues)
- `make eval` runs end-to-end against the live index

## Future Considerations

- **Phase 3 comparison:** Run eval with `all-MiniLM-L6-v2`, `BAAI/bge-base-en-v1.5`, and `text-embedding-3-small` to pick a winner
- **Temporal/recency weighting:** The eval framework doesn't yet account for recency — grocery list queries may need a time-decay boost in retrieval, not just embedding quality
- **LLM answer eval:** Could add GPT-based answer quality scoring on top of retrieval metrics
- **Auto-reindex on model change:** Currently logs a warning; could auto-trigger full reindex
