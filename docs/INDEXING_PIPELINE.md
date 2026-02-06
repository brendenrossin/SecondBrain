# Indexing Pipeline (Chunking → Embeddings → Hybrid Search)

## 1) Vault ingestion
### Inputs
- Vault root path (local folder)
- Include patterns: `**/*.md`
- Exclude: `.obsidian/`, `.trash/`, `node_modules/`, etc.

### Outputs
- Parsed Note records
- Raw text ready for chunking

## 2) Markdown-aware chunking
### Goals
- Preserve semantic boundaries (headings/bullets/code blocks)
- Avoid tiny chunks
- Keep stable IDs (so incremental re-indexing is cheap)
- Produce chunks that work well for both semantic search and citation

### Suggested algorithm (POC → V1)
1. Parse markdown into a lightweight structure:
   - heading tree (H1/H2/H3…)
   - paragraph blocks
   - bullet/list blocks
   - fenced code blocks
2. Chunk by semantic units, in this order of preference:
   - split on heading boundaries first
   - keep bullet lists intact when possible
   - keep fenced code blocks intact
   - combine consecutive short paragraphs until near target size
3. Enforce chunk size (baseline; tune later):
   - **target**: ~700 characters
   - **overlap**: ~100 characters
   - **min chunk**: ~100 characters
   - If a section is huge, split by paragraph boundaries while repeating `heading_path` metadata.

### Smart separators (Recursive strategy)
Use a recursive separator list that prefers natural markdown boundaries:
1) `\n# `, `\n## `, `\n### ` (headers)
2) `\n\n` (paragraphs)
3) `\n- ` / `\n* ` / `\n1. ` (lists)
4) `\n` (line breaks)
5) `. `, `? `, `! `, `; `, `: ` (sentence-ish boundaries)

### Stable chunk identity
Create stable chunk IDs so you can diff and upsert incrementally:
- `chunk_id = sha1(note_path + heading_path + chunk_index + chunk_text_normalized)`
- Store a `checksum = sha1(chunk_text_normalized)` to detect edits

### Store with each chunk
- `note_path`
- `note_title`
- `heading_path` (e.g., `["Project", "Architecture", "Indexing"]`)
- `chunk_index` (order within note)
- `chunk_text`
- `checksum`
- `token_count` (optional)
- `created_at` / `updated_at` (optional)

## 3) Embeddings (with optional contextualization)
### Model choice
Configurable via `SECONDBRAIN_EMBEDDING_PROVIDER` ("local" or "openai"):
- **Local (default):** BAAI/bge-base-en-v1.5 (768d) via sentence-transformers — best local accuracy
- **OpenAI API:** text-embedding-3-small (1536d, configurable via `SECONDBRAIN_OPENAI_EMBEDDING_DIMENSIONS`)
- BGE models use a query prefix (`"Represent this sentence for searching relevant passages: "`) automatically via `embed_query()` vs `embed()` for documents
- Model name is stored in ChromaDB collection metadata; mismatch triggers a warning on startup

### Baseline embedding strategy
- Embed **chunks** (not whole notes)
- Cache embeddings by `checksum` (so unchanged chunks don’t re-embed)

### Contextualized embeddings (recommended)
Instead of embedding raw chunks, prepend a short, LLM-generated context sentence to each chunk **before** embedding.
This improves retrieval for ambiguous chunks (e.g., “it”, “this system”, small lists) by injecting document identity + local continuity.

**Context prefix inputs**
- Document identity: file name / note title
- Frontmatter metadata: tags, type, description (if present)
- Lookback: previous 1–3 chunks (for continuity)

**Prompt (shape)**
- Output: **one sentence** describing what this chunk is about and where it fits in the note.
- Keep it short; no extra formatting.

**Resulting text to embed**
- `context_sentence + "\n\n" + original_chunk_text`

**Operational notes**
- Generate context prefixes in small batches (e.g., 10 chunks) to respect rate limits
- Embedding batch size can be larger (e.g., 100 chunks) depending on provider
- Store both:
  - `chunk_text_original`
  - `chunk_text_contextualized` (what gets embedded)
  - `context_sentence` (for debugging)

## 4) Lexical index (BM25)
### POC
- SQLite FTS5 over chunk text + note title

### V1+
- Meilisearch/OpenSearch with:
  - filters (path/type/topics)
  - synonyms (optional)

## 5) Hybrid retrieval
### Strategy (baseline)
1. Lexical retrieve top **K_lex** (e.g., 50)
2. Vector retrieve top **K_vec** (e.g., 30)
3. Merge candidates (e.g., RRF or min-max normalization)
4. Apply gates/filters (similarity threshold, metadata filters)
5. Optional LLM rerank to improve precision
6. Return top results with citations

### Defaults to start with
- `K_vec = 30`
- `K_lex = 50`
- `rerank_top_k = 10`
- `top_n = 5`

### Candidate merging
- Prefer **Reciprocal Rank Fusion (RRF)** for simplicity and strong performance
  - Merge lexical + vector lists using RRF score

### Similarity threshold gating
Avoid returning results “just to return something.”
- Apply a cosine similarity threshold to vector results before reranking
- If nothing passes threshold, return `NO_RESULTS` (and optionally suggest query refinement)

### Optional query transformation (later)
Can improve retrieval when queries are conversational or contain pronouns.
- Resolve pronouns where possible
- Expand with key entities from conversation context
- Prefer descriptive keywords over filler

### LLM reranking (recommended)
After merging/gating, rerank the best candidates using an LLM as a cross-encoder-style scorer.
- Input: query + candidate chunk (plus a short citation header)
- Output: relevance score (0–10)
- Re-sort by score desc
- Return `top_n` chunks

**Example flow**
- Retrieve `K_vec=30`
- Merge with lexical
- Take best `rerank_top_k=10`
- LLM scores each 0–10
- Return `top_n=5`

### Return payload
Return top results with:
- snippet highlights
- note path/title
- chunk `heading_path`
- similarity score + rerank score
- citations (stable links to file + section)

## 6) Citation format
Return machine-usable citations:
- `note_path`
- `heading_path`
- `chunk_id`
- `char_range` or `line_range` (optional)

UI can open the note at the right place.

## 6.1) Retrieval evaluation
Implemented in `src/secondbrain/eval/`. Run with `make eval`.

### Ground truth queries
Defined in `src/secondbrain/eval/eval_queries.yaml` — YAML with query, expected notes, and tags for filtering.

### Metrics computed (retrieval-only, no LLM answer eval)
- **Recall@K** (K=5, 10): fraction of expected notes in top-K results
- **Precision@5**: fraction of top-5 results that are relevant
- **MRR** (Mean Reciprocal Rank): how high the first relevant result ranks
- Per-query pass/fail breakdown with hits and misses

### Per-query labels (runtime)
- `PASS`: at least one result meets similarity + rerank thresholds
- `HALLUCINATION_RISK`: high vector similarity but low rerank score
- `NO_RESULTS`: nothing above similarity threshold
- `IRRELEVANT`: candidates retrieved but fail rerank threshold

### Output
- Human-readable table to stdout
- JSON report saved to `data/eval/<model>-<timestamp>.json` for cross-model comparison

## 7) Incremental indexing
- Use filesystem watcher (watchdog) OR scheduled scan with mtimes
- For changed file:
  - if chunk text changed (checksum differs):
    - regenerate `context_sentence` (if using contextualized embeddings)
    - re-embed and upsert
  - re-parse → re-chunk → diff chunks by ID/checksum
  - upsert changed chunks
  - delete removed chunks
- Keep a queue; coalesce rapid edits

## 8) Attachment strategy (later)
- Store attachment metadata
- Optional OCR pipeline for PDFs/images
- Treat attachment text as separate “documents” with their own chunks
