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
- Preserve semantic boundaries (headings/bullets)
- Avoid tiny chunks
- Keep stable IDs

### Suggested algorithm (POC)
1. Parse headings into a tree
2. For each section:
   - keep bullet lists intact
   - combine consecutive paragraphs
3. Enforce chunk size:
   - target 300–800 tokens
   - hard cap ~1200 tokens
4. If a section is huge, split by paragraphs while repeating heading_path metadata

### Store with each chunk
- `heading_path`
- `chunk_text`
- `checksum`

## 3) Embeddings
### Model choice
- Local option: sentence-transformers (fast, private)
- Hosted option: embedding API (quality)

### Embedding strategy
- Embed chunks (not whole notes)
- Cache embeddings by chunk checksum

## 4) Lexical index (BM25)
### POC
- SQLite FTS5 over chunk text + note title

### V1+
- Meilisearch/OpenSearch with:
  - filters (path/type/topics)
  - synonyms (optional)

## 5) Hybrid retrieval
### Strategy
1. Lexical retrieve top K_lex (e.g., 50)
2. Vector retrieve top K_vec (e.g., 50)
3. Merge with score normalization
4. Optional rerank top N (e.g., 20) using cross-encoder or LLM reranker
5. Return top results with:
   - snippet highlights
   - note path/title
   - chunk heading_path
   - citations (stable links to file + section)

### Score normalization
- Min-max per channel
- Or reciprocal rank fusion (RRF) (simple and strong)

## 6) Citation format
Return machine-usable citations:
- `note_path`
- `heading_path`
- `chunk_id`
- `char_range` or `line_range` (optional)

UI can open the note at the right place.

## 7) Incremental indexing
- Use filesystem watcher (watchdog) OR scheduled scan with mtimes
- For changed file:
  - re-parse → re-chunk → diff chunks by ID/checksum
  - upsert changed chunks
  - delete removed chunks
- Keep a queue; coalesce rapid edits

## 8) Attachment strategy (later)
- Store attachment metadata
- Optional OCR pipeline for PDFs/images
- Treat attachment text as separate “documents” with their own chunks
