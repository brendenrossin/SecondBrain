# Roadmap — POC → V1 → V2

## Guiding principles
- Ship in thin vertical slices: Ingest → index → retrieve → cite → synthesize
- Vault is the single source of truth — no state outside it
- Suggestion-only: the system recommends, never acts
- Simple, maintainable systems over clever or fragile ones
- Local-first, privacy-preserving

---

## Decisions Log

Captured 2026-02-07 after roadmap review session. The original brainstorm (with ChatGPT) produced a large design space. This section records what was kept, cut, and why.

| Decision | Rationale |
|----------|-----------|
| **Cut Phase 3.6 (Task lifecycle engine)** | Creates source-of-truth conflict with vault-driven architecture. The state machine (todo/doing/blocked/waiting/done) adds maintenance debt disproportionate to value. Current heuristics (days_open, due_date) cover the need. See `docs/features/DEFERRED-task-lifecycle.md`. |
| **Cut Phase 8 (Ambient intelligence)** | Email, calendar, and digest are three separate integration explorations, not a single phase. Extracted to individual exploration docs. |
| **Scoped down Phase 3.5** | Removed memory aging buckets (unnecessary abstraction) and "On this day" (low impact). Kept retrieval transparency and context-aware recency. |
| **Scoped down Phase 3.7** | Removed contradiction detection (research problem, low precision) and drift detection (requires state tracking we don't have). Kept escalation and recurrence signals. |
| **Recency handling** | Not a scoring multiplier. When two similar notes exist (e.g., two grocery lists), the LLM should contextually prefer the recent one during synthesis. No decay formula needed. |
| **Marked Phase 4 done** | Tailscale is live. Remote access from phone works. |
| **Replaced old Phase 5 (bot gateway) with retrieval transparency** | Next.js frontend already has a working `/chat` page. Bot gateway is unnecessary. Current Phase 5 is retrieval transparency + context-aware recency. |
| **Deprecated Gradio UI** | Next.js frontend is the sole UI going forward. Gradio code can be removed. |
| **Vault stays authoritative** | No task state, signal state, or other application state outside the vault and its derived indexes. The system is always a read-only view on top of personal notes. |
| **Voice chat: resolve open questions for v1** | Single voice default (alloy, no UI picker). Fresh sessions (no text history injection). Error on offline (no Whisper STT fallback). Server VAD only (no push-to-talk). Keep reranker enabled but monitor latency. See resolved decisions in `docs/features/voice-chat-realtime-api.md`. |

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

## Phase 3 — Metadata extraction + suggestions ✅
- [x] Extract:
  - summaries
  - key phrases
  - entities (person/org/product)
  - dates/deadlines
  - action items
- [x] Confidence scores + provenance
- [x] MetadataStore (SQLite WAL, same patterns as other stores)
- [x] LLM-based extraction pipeline (Ollama-first, OpenAI-fallback)
- [x] Incremental extraction (content hash comparison)
- [x] Suggestion engine (related notes, links, tags)
- [x] API endpoints: /metadata, /extract, /suggestions, /entities, /action-items
- [x] "Insights" tab in Gradio UI (summary, entities, dates, action items)
- [x] "Suggestions" tab in Gradio UI (related notes, suggested links, suggested tags)
- [x] Daily sync integration (extraction runs after reindex)
- [x] `make extract` command

Deliverable: system becomes a "memory assistant," not just search.

---

## Phase 3.5 — Next.js frontend + UI redesign ✅
- [x] Next.js frontend with dark "mission control" dashboard
- [x] Tasks page with stat cards, filters, category tree
- [x] Calendar/agenda page with weekly view
- [x] Chat page with RAG integration
- [x] Task aggregator with bi-directional sync to vault
- [x] Tailwind + glass-card design system
- [x] Skeleton loading, empty states, micro-interactions

Deliverable: polished, modern frontend replacing Gradio.

---

## Phase 4 — Secure remote access ✅
- [x] Tailscale VPN for private network access
- [x] Mobile access from phone via Tailscale
- [x] No public endpoints exposed

Deliverable: query your memory from your phone safely.

---

## Phase 5 — Retrieval transparency + context-aware recency (~1 week)
Goal: make retrieval results explainable and let the LLM handle recency contextually.

- [ ] Add score breakdown to `/ask` API response:
  - lexical score, vector score, rerank score per citation
- [ ] "Why this result" expandable section in Next.js chat UI
- [ ] Context-aware recency: when multiple similar notes exist (e.g., two grocery lists), the LLM uses note dates during synthesis to prefer the recent one
  - No decay formula or scoring multiplier
  - Pass note timestamps to the LLM as context; let it reason about recency
  - Foundational notes (decisions, specs, architecture) are never penalized

Deliverable: transparent ranking + LLM-driven recency awareness.

See `docs/features/retrieval-transparency.md` for full spec.

---

## Phase 5.5 — Voice chat via OpenAI Realtime API (~2-3 weeks)
Goal: hands-free voice interaction with the knowledge base using speech-to-speech.

- [ ] Backend WebSocket relay (`/api/v1/voice`) proxying audio to OpenAI Realtime API
- [ ] `gpt-realtime-mini` model (cost-efficient, strong tool calling)
- [ ] Tool call interception: `search_knowledge_base` calls existing RAG pipeline
- [ ] Frontend audio capture/playback via AudioWorklet + Web Audio API (Mac + iPhone)
- [ ] User interrupt / barge-in: flush playback queue on `speech_started`, conditional `response.cancel` + `conversation.item.truncate` with tracked `audio_end_ms`
- [ ] Response state machine: `idle` → `in_progress` → `done` | `interrupted`
- [ ] Microphone button in chat UI (opt-in, text input remains default)
- [ ] Server VAD for natural turn-taking
- [ ] JSONL event logging (transcripts, tool calls, interrupts, errors)
- [ ] Feature flag: `SECONDBRAIN_VOICE_ENABLED` (default off)

Deliverable: talk to your vault hands-free from any device.

See `docs/features/voice-chat-realtime-api.md` for full spec.

---

## Phase 6 — Proactive signals v1 (~1–2 weeks)
Goal: daily passive insights that recommend, never act. High precision, low volume.

- [ ] Post-sync signal pipeline (runs after daily indexing/extraction)
- [ ] Escalation signals: approaching/overdue deadlines (data already exists)
- [ ] Recurrence signals: same topic/entity appearing repeatedly across recent notes
- [ ] Signal schema: `type, summary, confidence, evidence[], suggested_next_step`
- [ ] Dashboard integration: 1–3 highest-confidence signals per day
- [ ] One-click actions: create task in vault / dismiss
- [ ] Safety: signals are suggestions only; no side effects; high confidence threshold

Deliverable: the system surfaces what matters without being noisy.

See `docs/features/proactive-signals-v1.md` for full spec.

---

## Phase 7 — Knowledge graph (V2, 4–8+ weeks)
- [ ] Choose graph store (Neo4j or Postgres)
- [ ] Entity resolution + dedupe
- [ ] Relationship extraction (LLM-assisted, human-reviewed)
- [ ] Graph exploration UI:
  - "show related concepts"
  - "what changed over time"
  - "decisions and constraints"

Deliverable: true navigable concept graph, beyond similarity search.

---

## Phase 8 — Write-back workflow (V2+)
- [ ] PR-style changesets
- [ ] Apply suggested links/tags to Markdown files
- [ ] Versioning + rollback

Deliverable: assistant can help maintain your vault structure safely.

---

## Future explorations (not committed)
These ideas have potential but need separate feasibility assessments before entering the roadmap.

- **Email ingestion (read-only)** — See `docs/features/EXPLORATION-email-ingestion.md`
- **Calendar integration (read-only)** — See `docs/features/EXPLORATION-calendar-integration.md`
- **Daily digest** — Depends on proactive signals (Phase 6); trivial if signals ship
- **Task lifecycle engine** — See `docs/features/DEFERRED-task-lifecycle.md`

---

## Deprecated
- **Gradio UI** — Replaced by Next.js frontend (Phase 3.5). Code can be removed.
- **Bot gateway / chat interface (old Phase 5)** — Absorbed by Next.js `/chat` page.

---

## Definition of done (each phase)
- Automated tests for core paths
- Deterministic rebuild from vault
- Security checklist satisfied for any exposed endpoint
- Observability in place (logs/metrics)
