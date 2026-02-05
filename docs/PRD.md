# PRD — Obsidian Semantic Memory + Knowledge Graph Assistant

## 1) Overview
Build a personal “memory layer” on top of an Obsidian vault that:
- Ingests Markdown notes (and optionally attachments)
- Produces embeddings + metadata + suggested links/tags
- Supports **fast, accurate retrieval** via hybrid search
- Optionally builds a **knowledge graph** (entities + relationships)
- Enables interaction **from anywhere** (secure web + chat interface)
- Remains **local-first, privacy-respecting**, and secure by design

### Non-goals (initially)
- Fully autonomous auto-editing of notes (write-backs are opt-in)
- “Perfect” ontology for everything you write
- Multi-user collaboration (v2+)
- Full-text OCR of all PDFs/images (optional later)

## 2) Users & key use cases
### Primary user
- Single technically capable user (you) with a Mac Studio “home base”
- Notes originate via dictation (WhisperFlow) and manual writing in Obsidian

### Core use cases
1. **Semantic recall**
   - “What did I decide about the engagement ring prongs?”
   - “Find the note where I compared vendors for lab diamonds.”
2. **Cross-note synthesis**
   - “Summarize my ring requirements and open questions.”
   - “What are the remaining action items and deadlines?”
3. **Auto-link suggestions**
   - Suggest backlinks between notes that share meaning but lack explicit `[[links]]`
4. **Structured tracking**
   - Convert scattered notes into canonical “spec pages” + timeline
5. **Mobile access**
   - Query memory via secure web or chat when away from the Mac Studio
6. **Auditability**
   - Show sources for every answer (citations to notes/chunks)

## 3) Success metrics
### POC metrics (2–4 weeks)
- Indexing completes reliably on your vault
- Query latency: < 1–2s locally for typical questions
- Retrieval quality: top-5 results contain the right note ≥ 80% for a curated set of 50 queries
- Zero data loss; reproducible rebuild from source vault

### V1 metrics (6–10 weeks)
- Hybrid retrieval improves “right answer in top-5” by ≥ 10–20% over pure vector
- Entity extraction produces usable tags/entities with low hallucination (human acceptance ≥ 70%)
- Secure remote access functioning (2FA/passkeys; audit log; IP allowlist optional)

### V2 metrics (later)
- Knowledge graph improves navigation/synthesis in measurable ways:
  - fewer follow-up queries to locate related info
  - better “what’s connected to X?” exploration
- Low-friction write-back suggestions (opt-in) with high acceptance rate

## 4) Requirements

### Functional requirements
**Ingestion**
- Watch vault folder for changes (file watcher) OR scheduled scans
- Parse Markdown frontmatter + body; capture file metadata
- Support incremental re-indexing (changed files only)

**Chunking**
- Markdown-aware chunking:
  - preserve headings
  - keep bullets together
  - stable chunk IDs so diffs don’t explode the index

**Embeddings**
- Pluggable embedder:
  - local model option (privacy)
  - hosted option (quality/cost)
- Store per-chunk embedding vectors

**Hybrid retrieval**
- BM25 (lexical) + vector similarity
- Reranking (optional) with cross-encoder / LLM reranker
- Result explanations + citations

**Metadata extraction**
- Lightweight automatic:
  - title, summary, key phrases
  - entities (people/places/products/projects)
  - timestamps/dates mentioned
  - action items (“TODO-like”)
- Confidence scores + provenance

**Knowledge graph (optional in POC, planned for V1/V2)**
- Nodes: Note, Chunk, Entity, Concept
- Edges: mentions, related_to, part_of, decided, constraints, next_step
- Populate from extraction + co-occurrence + semantic similarity

**Interfaces**
- Local:
  - CLI + minimal web UI (localhost)
- Remote (opt-in):
  - secure web UI (TLS, auth)
  - chat interface (Telegram/WhatsApp-style) via a bot gateway

**Write-backs (opt-in)**
- Create “suggested links/tags” report
- Allow one-click apply (later) or manual copy/paste

### Non-functional requirements
- **Security**: encryption in transit + at rest; strict auth; secrets hygiene
- **Privacy**: local-first, user-controlled; explicit toggles for any cloud use
- **Reliability**: resumable indexing; backups; deterministic rebuild
- **Performance**: fast incremental updates; caching; background indexing
- **Portability**: vault remains plain files; system can be replaced without lock-in
- **Observability**: logging, tracing, metrics; visibility into failures

## 5) MVP scope definition (POC)
### Must-haves
- Ingest vault Markdown
- Chunk + embed + store in vector DB
- BM25 index
- Hybrid search endpoint
- Simple UI (CLI or localhost web)
- Source citations

### Should-haves
- Incremental re-indexing
- Basic metadata extraction (summary + keywords)
- “Related notes” suggestions

### Won’t-haves (POC)
- Full knowledge graph with Neo4j
- Bot integrations
- Auto write-back edits

## 6) Competitive/adjacent solutions (for inspiration, not dependency)
- Personal knowledge management tools (e.g., “AI note apps”)
- RAG frameworks (LlamaIndex/LangChain)
- Graph DBs (Neo4j) + embeddings
- Local-first assistants

## 7) Risks & mitigations
- **Hallucinated metadata/links** → require confidence + human approval, never auto-edit by default
- **Security exposure via remote access** → start local-only; add remote with strong auth + network hardening
- **Index drift** (unstable chunking) → stable chunk IDs + incremental diffing
- **Cost creep** (hosted embeddings/LLMs) → local models + caching; measure token usage

## 8) Milestones (high-level)
- POC: index + hybrid search + citations (local)
- V1: incremental updates + entity extraction + suggestions UI + secure remote web
- V1.5: chat interface + rate limiting + audit logs
- V2: knowledge graph + graph exploration UI + write-back workflow
