# RAG-2 + RAG-3: Caching Layer + Vault Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add context blurb + embedding caches to avoid recomputation during re-indexes, and generate a vault-level manifest injected into the answerer system prompt so the LLM knows what topics the vault covers.

**Architecture:** New `IndexCache` store (SQLite) with two tables — `blurb_cache` keyed on `(chunk_text_hash, model)` and `embedding_cache` keyed on `(embedding_text_hash, model)`. New `ManifestGenerator` builds a text summary from indexed notes/chunks. Manifest injected into `Answerer.SYSTEM_PROMPT` at query time.

**Tech Stack:** SQLite (WAL mode), existing Anthropic SDK, existing embedder

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/secondbrain/stores/index_cache.py` | `IndexCache` — blurb + embedding cache store |
| Create | `src/secondbrain/indexing/manifest.py` | `ManifestGenerator` — vault-level summary |
| Modify | `src/secondbrain/indexing/context.py` | Check blurb cache before LLM call |
| Modify | `src/secondbrain/api/index.py` | Wire caches into pipeline, generate manifest after indexing |
| Modify | `src/secondbrain/api/dependencies.py` | Add `get_index_cache`, update `get_answerer` |
| Modify | `src/secondbrain/synthesis/answerer.py` | Accept + inject vault manifest into system prompt |
| Create | `tests/test_index_cache.py` | Cache + manifest tests |

---

### Task 1: Implement IndexCache store (blurb + embedding cache)

**Files:** Create `src/secondbrain/stores/index_cache.py`, Create `tests/test_index_cache.py`

- [ ] Write tests for IndexCache: get/set blurb cache, get/set embedding cache, cache miss returns None, cache hit returns stored value
- [ ] Implement `IndexCache` with SQLite schema:
  - `blurb_cache(text_hash TEXT, model TEXT, blurb TEXT, PRIMARY KEY(text_hash, model))`
  - `embedding_cache(text_hash TEXT, model TEXT, embedding BLOB, PRIMARY KEY(text_hash, model))`
  - Standard WAL + reconnect pattern matching other stores
  - Methods: `get_blurb(text_hash, model)`, `set_blurb(text_hash, model, blurb)`, `get_embedding(text_hash, model)`, `set_embedding(text_hash, model, embedding)`, `clear()`
  - Embeddings stored as numpy `.tobytes()` / `np.frombuffer()`
- [ ] Run tests, verify pass
- [ ] Commit

---

### Task 2: Wire blurb cache into ContextGenerator

**Files:** Modify `src/secondbrain/indexing/context.py`, Modify `tests/test_index_cache.py`

- [ ] Add `index_cache: IndexCache | None = None` param to `ContextGenerator.__init__`
- [ ] In `_generate_one()`: before LLM call, hash `chunk.chunk_text` and check `index_cache.get_blurb(hash, model)`. On hit, return cached blurb (skip LLM). On miss, call LLM as before, then `index_cache.set_blurb(hash, model, blurb)`.
- [ ] Write test: verify cached blurb skips LLM call on second invocation
- [ ] Run tests, verify pass
- [ ] Commit

---

### Task 3: Wire embedding cache into indexing pipeline

**Files:** Modify `src/secondbrain/api/index.py`, Modify `tests/test_index_cache.py`

- [ ] In `_run_indexing()`, after `build_embedding_text()`, check embedding cache before calling `embedder.embed()`. For each text, hash it and check cache. Collect cache misses, embed only those, store results back.
- [ ] Add `index_cache` param to `_run_indexing()` signature
- [ ] Write test: structural test verifying index.py references IndexCache
- [ ] Run tests, verify pass
- [ ] Commit

---

### Task 4: Implement ManifestGenerator + inject into Answerer

**Files:** Create `src/secondbrain/indexing/manifest.py`, Modify `src/secondbrain/synthesis/answerer.py`, Modify `tests/test_index_cache.py`

- [ ] Implement `ManifestGenerator`:
  - Method: `generate_manifest(lexical_store: LexicalStore) -> str`
  - Queries all distinct `(note_path, note_title, note_folder)` from chunks table
  - Groups by folder, lists note titles with heading paths
  - Output format: "Your knowledge base contains: [folder]: [note1], [note2]..."
  - Compact text, ~200-500 tokens max
- [ ] Modify `Answerer.__init__` to accept `vault_manifest: str | None = None`
- [ ] In `answer()` and `answer_stream()`, inject manifest between SYSTEM_PROMPT and SOURCES — for both Anthropic and OpenAI paths
- [ ] Write tests: ManifestGenerator produces expected format, Answerer includes manifest in system text
- [ ] Run tests, verify pass
- [ ] Commit

---

### Task 5: Wire everything into dependencies + index endpoint, full verification

**Files:** Modify `src/secondbrain/api/dependencies.py`, Modify `src/secondbrain/api/index.py`

- [ ] Add `get_index_cache()` to dependencies.py (lru_cache, `data_path / "index_cache.db"`)
- [ ] Update `index_vault()` to create IndexCache, pass to ContextGenerator and `_run_indexing`
- [ ] After indexing completes, generate manifest and store it (file or in-memory via dependency)
- [ ] Update `get_answerer()` to load manifest and pass to Answerer
- [ ] Run full test suite, lint, format, mypy
- [ ] Smoke test: restart server, trigger re-index, verify caches populated and manifest in answerer
- [ ] Commit
