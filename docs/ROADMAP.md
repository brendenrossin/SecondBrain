# Roadmap — POC → V1 → V2

## Guiding principle
Ship in thin vertical slices:
- Ingest → index → retrieve → cite → (optional) synthesize
Avoid “graph perfection” early.

---

## Phase 0 — Repo + scaffolding (1–2 days)
- [ ] Create repo structure
- [ ] CI linting + type checks
- [ ] Config system (env + YAML)
- [ ] Local dev tooling (Makefile / task runner)

Deliverable: run `make dev` and see a hello-world API.

---

## Phase 1 — POC indexing + retrieval (1–2 weeks)
### 1.1 Vault ingestion
- [ ] Read vault path; enumerate Markdown files
- [ ] Parse frontmatter (YAML) + body
- [ ] Store note metadata in SQLite/Postgres

### 1.2 Chunking
- [ ] Markdown-aware chunker (headings + bullets)
- [ ] Stable chunk IDs (hash of note path + heading path + block offsets)

### 1.3 Embeddings + vector store
- [ ] Choose embedder (local or hosted)
- [ ] Store vectors in Chroma/Qdrant/pgvector
- [ ] Store chunk text + note refs

### 1.4 Lexical search
- [ ] SQLite FTS5 (POC) or Meilisearch
- [ ] Index note/chunk text

### 1.5 Hybrid retrieval API
- [ ] `POST /query` returning:
  - top chunks
  - note titles/paths
  - short highlights
  - citations

### 1.6 Minimal UI
- [ ] CLI command: `memory ask "..."` prints citations
- [ ] Optional: localhost web page

Deliverable: ask questions and reliably get the right notes back.

---

## Phase 2 — Quality improvements (2–4 weeks)
- [ ] Incremental indexing (watcher + queue)
- [ ] Reranking (cross-encoder) for top N results
- [ ] Caching embeddings; batch jobs; rate limits

Deliverable: faster updates + better ranking.

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
