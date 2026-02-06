# Roadmap — POC → V1 → V2

## Guiding principle
Ship in thin vertical slices:
- Ingest → index → retrieve → cite → (optional) synthesize
Avoid “graph perfection” early.

---

## Phase 0 — Repo + scaffolding ✅
- [x] Create repo structure
- [x] CI linting + type checks
- [x] Config system (env + pydantic-settings)
- [x] Local dev tooling (Makefile)

Deliverable: run `make dev` and see a hello-world API.

---

## Phase 1 — POC indexing + retrieval ✅
### 1.1 Vault ingestion
- [x] Read vault path; enumerate Markdown files
- [x] Parse frontmatter (YAML) + body
- [x] Store note metadata in SQLite

### 1.2 Chunking
- [x] Markdown-aware chunker (headings + bullets)
- [x] Stable chunk IDs (hash of note path + heading path + block offsets)

### 1.3 Embeddings + vector store
- [x] Multi-provider embedder (local sentence-transformers + OpenAI API)
- [x] Default: BAAI/bge-base-en-v1.5 (768d, local)
- [x] Store vectors in ChromaDB with model metadata tracking
- [x] Store chunk text + note refs

### 1.4 Lexical search
- [x] SQLite FTS5
- [x] Index note/chunk text

### 1.5 Hybrid retrieval API
- [x] `POST /ask` with hybrid search (RRF), LLM reranking, answer synthesis

### 1.6 UI
- [x] Gradio mobile-first chat interface with local/OpenAI provider toggle

Deliverable: ask questions and reliably get the right notes back.

---

## Phase 2 — Quality improvements ✅
- [x] Incremental indexing (index tracker with content hashing)
- [x] LLM reranking for top N results (gpt-4o-mini or local Ollama)
- [x] RAG evaluation framework (Recall@K, Precision@K, MRR) with YAML test queries
- [x] Embedding model upgrade: MiniLM → BGE (Recall@5: 0.710 → 0.783)
- [x] Multi-provider embedding support (local + OpenAI API)
- [x] Model mismatch detection in vector store

Deliverable: faster updates + better ranking + measurable retrieval quality.

---

## Phase 3 — Metadata extraction + suggestions (2–4 weeks)
- [ ] Extract:
  - summaries
  - key phrases
  - entities (person/org/product)
  - dates/deadlines
  - action items
- [ ] Confidence scores + provenance
- [ ] “Suggestions report” UI:
  - related notes
  - suggested `[[links]]`
  - suggested tags

Deliverable: system becomes a “memory assistant,” not just search.

---

## Phase 4 — Secure remote access (2–4 weeks)
Pick one:
- Tailscale/WireGuard VPN
- Cloudflare Tunnel (zero trust)
- SSH reverse tunnel

- [ ] Auth (OIDC or passkeys)
- [ ] Rate limiting + audit logs
- [ ] Mobile-friendly UI

Deliverable: you can query your memory from your phone safely.

---

## Phase 5 — Chat interface (optional, 2–4 weeks)
- [ ] Bot gateway service
- [ ] Command handling + conversation state
- [ ] Strict grounding + citations
- [ ] Abuse controls (rate limit; allowlist)

Deliverable: “ask my vault” from chat.

---

## Phase 6 — Knowledge graph (V2, 4–8+ weeks)
- [ ] Choose graph store (Neo4j or Postgres)
- [ ] Entity resolution + dedupe
- [ ] Relationship extraction (LLM-assisted, human-reviewed)
- [ ] Graph exploration UI:
  - “show related concepts”
  - “what changed over time”
  - “decisions and constraints”

Deliverable: true navigable concept graph, beyond similarity search.

---

## Phase 7 — Write-back workflow (V2+)
- [ ] PR-style changesets
- [ ] Apply suggested links/tags to Markdown files
- [ ] Versioning + rollback

Deliverable: assistant can help maintain your vault structure safely.

---

## Definition of done (each phase)
- Automated tests for core paths
- Deterministic rebuild from vault
- Security checklist satisfied for any exposed endpoint
- Observability in place (logs/metrics)
