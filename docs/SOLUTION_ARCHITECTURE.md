# Solution Architecture — Obsidian Semantic Memory + Knowledge Graph Assistant

## 1) Architecture goals
- Local-first by default (vault stays on your machine)
- Pluggable models/stores (swap without rewriting everything)
- Secure remote access (opt-in) without exposing vault directly
- Auditability: every answer includes sources

## 2) Logical components
1. **Vault Connector**
   - Reads Markdown + frontmatter
   - Watches filesystem for changes (optional)
2. **Indexer**
   - Markdown-aware chunker
   - Embedding generator
   - BM25 builder
   - Metadata/entity extractor (optional)
3. **Stores**
   - Document store (SQLite/Postgres)
   - Vector store (pgvector/Qdrant/Weaviate/Chroma)
   - Lexical store (BM25 via OpenSearch/Meilisearch/SQLite FTS)
   - Graph store (optional): Neo4j / Postgres graph tables
4. **Retrieval Service**
   - Hybrid search + reranking
   - Citation assembly
5. **Answer Service**
   - Optional LLM synthesis (with strict grounding)
   - Structured outputs (summary, action items, constraints)
6. **Interfaces**
   - Next.js web UI (localhost + Tailscale remote access)
   - Gradio UI (deprecated — replaced by Next.js)

## 3) Deployment modes (pick one per phase)

### Mode A — Local-only (POC recommended)
**Where everything runs:** Mac Studio
- Indexer runs on schedule or file change
- Query API binds to localhost only
- UI is local web or CLI

**Pros**
- Easiest security story
- No public exposure
- Lowest ops overhead

**Cons**
- Not accessible away from home unless you VPN in

### Mode B — Local core + Secure Remote Access (V1 recommended)
**Core stays local**, but you can query remotely via:
- Tailscale / WireGuard VPN
- Or Cloudflare Tunnel with strict auth
- Or SSH tunnel + reverse proxy

**Pros**
- Still local-first
- Minimal cloud footprint
- Remote access without opening ports publicly

**Cons**
- Requires networking setup
- Mobile experience depends on tunnel/VPN reliability

### Mode C — Split compute (Indexer local, Query in cloud)
- Vault syncs to cloud storage (encrypted) OR periodically pushes an index snapshot
- Query service runs in cloud (container)
- Optionally keep raw text local and push only embeddings + doc IDs

**Pros**
- Fast global access
- Easier to run bots/web publicly

**Cons**
- Harder privacy story
- More ops + attack surface

### Mode D — Fully hosted (not recommended early)
- Everything in cloud; Obsidian vault stored there
- Highest risk/ops burden; only consider if you need multi-device native access and accept tradeoffs

## 4) Current architecture (as built)
### POC → V1 (Phases 0-4, done)
- Mode B (local core + Tailscale remote access)
- Stores: SQLite (WAL mode) + ChromaDB (local) + SQLite FTS5
- API: FastAPI (Python)
- UI: Next.js frontend (dark "mission control" dashboard)
- Remote access: Tailscale VPN
- Metadata extraction + task aggregation from vault

### V2 (planned)
- Add Neo4j (or Postgres graph tables) for KG
- Graph exploration UI
- Write-back workflow into vault (PR-style suggestions)

## 5) Technology options (opinionated)
### Language/runtime
- Python for ingestion/indexing + API (fast iteration)
- Next.js/TypeScript for frontend

### Vector store
- **pgvector** (if you want one database): simple, durable, ops-friendly
- **Qdrant**: great local + server mode, strong filtering, easy
- **Chroma**: fastest to start; less “production” feeling but fine for POC

### Lexical search
- SQLite FTS5 for POC
- Meilisearch / OpenSearch for V1+ (Meili is simpler)

### Knowledge graph
- Neo4j for rich graph queries and tooling
- Postgres graph tables if you want fewer moving parts

### Models
- Embeddings (multi-provider, configurable via `SECONDBRAIN_EMBEDDING_PROVIDER`):
  - **Default (local):** BAAI/bge-base-en-v1.5 (768d) — best local accuracy/speed tradeoff
  - **OpenAI API:** text-embedding-3-small (1536d, configurable dimensions)
  - BGE models use query-specific prefix for improved retrieval
  - Model metadata stored in ChromaDB; mismatch detection on startup
- Reranker:
  - LLM-based reranking (gpt-4o-mini or local Ollama)
- Generator:
  - LLM synthesis with strict grounding and citations (gpt-4o-mini or local Ollama)

## 6) Data flow
1. File change detected → enqueue file path
2. Parse Markdown → extract frontmatter + headings + blocks
3. Chunk → stable chunk IDs
4. Embed chunks → store vectors
5. Build lexical index (BM25/FTS)
6. Extract metadata/entities → store with confidence + provenance
7. Populate graph (optional) from entities + similarity + explicit links
8. Query → hybrid retrieve → rerank → return results (+ citations)
9. Optional: synthesis step generates answer grounded in retrieved chunks

## 7) Security boundaries
- Vault folder: never exposed directly to the internet
- Query API:
  - local-only in POC
  - behind VPN/tunnel + auth in V1
- Secrets:
  - stored in OS keychain or secrets manager (never in repo)
- Write-back:
  - separate permissioned endpoint; requires explicit user confirmation

## 8) Key design decisions to lock early
- Stable chunk IDs
- Incremental indexing strategy
- Grounding and citation format
- Auth model for remote access (passkeys/2FA)
