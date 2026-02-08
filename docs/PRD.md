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
   - Hands-free voice queries via OpenAI Realtime API (speech-to-speech with RAG tool calling)
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
  - Next.js web UI (localhost, served via launchd)
- Remote (opt-in):
  - Tailscale VPN for private network access (done)
  - Next.js frontend accessible from any Tailscale device
- Voice (opt-in):
  - Speech-to-speech via OpenAI Realtime API with RAG tool calling
  - Mic button in chat UI; browser audio I/O (Mac + iPhone + AirPods)
  - See `docs/features/voice-chat-realtime-api.md`

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
- POC: index + hybrid search + citations (local) *(done)*
- V1: incremental updates + entity extraction + suggestions UI + secure remote access *(done — Phases 0-4)*
- V1.5: retrieval transparency + proactive signals + voice chat *(next — Phases 5-6)*
- V2: knowledge graph + graph exploration UI + write-back workflow *(Phases 7-8)*

> **Note (2026-02-07):** The original V1.5 milestone ("chat interface + rate limiting + audit logs") is obsolete. The Next.js frontend includes a chat page, replacing the planned bot gateway. Gradio UI is deprecated.

## 9) Interaction layer (POC → V1)

### Goal
Provide a **clean, secure browser-based chat interface** for interacting with the Second Brain RAG system from anywhere, without exposing the system publicly or building custom auth in early phases.

This document defines the **reference interaction architecture** that an AI coding agent can implement quickly (≈1 week) and safely.

---

### Phase 1 (POC): Local-first web UI + private network access

**Architecture**
- Backend: local RAG service (FastAPI)
- UI: lightweight web chat (Gradio)
- Network access: private device network (Tailscale)

**Key properties**
- No public endpoints
- No custom authentication
- Access restricted to trusted devices
- Vault + embeddings remain local

**Why this approach**
- Minimizes security risk
- Fastest path to usable remote access
- Easy to reason about + debug
- Suitable for a single-user system

---

### Web UI requirements (Gradio)

**Functional scope**
- Single-page browser UI
- Text chat interface
- Multi-turn conversation with local persistence (SQLite or JSON file)
- Streaming LLM responses for responsive UX
- Explicit citation display for every response

**UI elements**
- Chat panel (left)
- Sources panel (right or expandable):
  - note title / file path
  - heading path
  - short snippet
  - similarity score + rerank score

**Non-goals (POC UI)**
- User accounts
- Settings dashboard
- Note editing or write-back
- Multi-user support

---

### API contract (reference)

**Endpoint**
- `POST /ask`

**Request**
```json
{
  "query": "string",
  "conversation_id": "optional-string",
  "top_n": 5
}
```

**Response**
```json
{
  "answer": "string",
  "conversation_id": "string",
  "citations": [
    {
      "note_path": "string",
      "note_title": "string",
      "heading_path": ["string"],
      "chunk_id": "string",
      "snippet": "string",
      "similarity_score": 0.0,
      "rerank_score": 0.0
    }
  ],
  "retrieval_label": "PASS | NO_RESULTS | IRRELEVANT | HALLUCINATION_RISK"
}
```

**Streaming variant**
- `POST /ask/stream` returns Server-Sent Events (SSE)
- Events: `citation` (sent first), `token` (streamed answer), `done` (final metadata)
```

---

### Security model (POC)

**Access control**
- Enforced at the network layer (Tailscale)
- Only trusted devices can reach the service
- MFA enabled via identity provider

**Application assumptions**
- Single trusted user
- No anonymous access
- No public DNS

**Threats intentionally out-of-scope (POC)**
- Credential stuffing
- Multi-user role separation
- External attacker probing

---

### Phase 2 (V1): Secure browser access without VPN (optional)

**Upgrade path**
- Add Cloudflare Tunnel in front of the local service
- Protect with Cloudflare Access (SSO + MFA)

**When to do this**
- If VPN-style access is undesirable
- If access is needed from unmanaged devices

---

### Explicit non-goals (until V2)
- Slack / Telegram / WhatsApp bots (bot gateway cut from roadmap — Next.js chat page serves the need)
- Public API exposure
- MCP-based tool execution
- Note write-back or auto-editing

---

### Implementation guidance for AI coding agents

When implementing this layer:
1. Favor simplicity over extensibility
2. Always return citations
3. Never answer without retrieval evidence unless explicitly requested
4. Log retrieval outcomes to local JSONL file (`data/queries.jsonl`):
   - timestamp, query, conversation_id, retrieval_label, citation_ids, latency_ms
5. Keep UI stateless where possible

This interaction layer is intended to be **replaceable** without affecting the core indexing or retrieval pipeline.
