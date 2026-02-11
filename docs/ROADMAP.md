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
| **Reprioritized roadmap based on real-world usage (2026-02-08)** | Tasks/scheduling is the most-used feature. Vault has ~16 notes — RAG infrastructure is solid but the bottleneck is capture volume, not retrieval quality. Reordered phases to maximize daily value: morning briefing → inbox/model upgrade → quick capture → weekly review → voice chat. Moved retrieval transparency and full proactive signals to deferred (morning briefing absorbs the core escalation value). |
| **Deferred vault health checks** | Premature with ~16 notes. Note matching during inbox processing prevents the duplication that would make health checks necessary. Revisit at 100+ notes. |
| **Inbox upgrade: resolve open questions** | Note matching restricted to `10_Notes/` and `30_Concepts/` only (not projects). Frontend toggle labeled "Claude" (specific, recognizable). See `docs/features/inbox-upgrade-anthropic-migration.md`. |

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

## Phase 5 — Morning Briefing Dashboard ✅
Goal: when you open the app, instantly know what your day looks like.

- [x] Dashboard card showing today's date and summary:
  - Overdue tasks (count + list)
  - Tasks due today
  - What you worked on yesterday (from yesterday's daily note Focus/Notes sections)
  - Aging follow-ups (tasks open > 3 days with no due date)
- [x] API endpoint: `GET /api/v1/briefing` assembling data from task aggregator + daily notes
- [x] Frontend: prominent card at top of Tasks page (or dedicated dashboard home)
- [x] No LLM needed — pure data assembly from existing task aggregator and daily notes

Deliverable: a 10-second daily check-in that replaces mentally scanning your todo list.

---

## Phase 5.5 — Inbox Upgrade + Anthropic Migration ✅
Goal: better input quality from dictation and stronger LLM across the system.

- [x] Rewrite segmentation prompt: retrieval-framed heuristic with few-shot examples for dictated text
- [x] Add Anthropic SDK: Claude Sonnet 4.5 for inbox processing (better classification of messy dictation)
- [x] Claude Haiku 4.5 for chat (reranker + answerer), replacing GPT-4o-mini as cloud option
- [x] Fallback chain: Anthropic → Ollama → OpenAI
- [x] Note matching: route new content to existing notes when topic already has a note in `10_Notes/` or `30_Concepts/`
- [x] Frontend: rename provider toggle from "OpenAI" to "Claude"

Deliverable: smarter ingestion + better chat quality + less note duplication.

See `docs/features/inbox-upgrade-anthropic-migration.md` for full spec.

---

## Phase 5.7 — User Configurability ✅
Goal: make the repo cloneable — a new user can customize branding, task categories, and vault layout without hunting through 10 files.

- [x] Frontend branding config: create `frontend/src/lib/config.ts` with `APP_NAME`, `USER_NAME`, `USER_INITIAL`; import in layout, sidebar, chat provider
- [x] Inbox processor constants: consolidate `TASK_CATEGORIES`, `LIVING_DOCUMENTS`, `VAULT_FOLDERS` at top of file with clear comments; interpolate into classification prompt
- [x] README setup section: 5-step guide for new users (env, vault folders, branding, categories, manifest)

Deliverable: clone → edit 2 files → working personal instance.

See `docs/features/user-configurability.md` for full spec.

---

## Phase 6 — LLM Cost Tracking + Admin Dashboard ✅
Goal: track input/output tokens and cost for every LLM API call; surface metrics in a new Admin dashboard page.

- [x] `UsageStore` (SQLite WAL): logs every LLM call with provider, model, tokens, cost
- [x] `calculate_cost()` pricing helper (Anthropic, OpenAI, Ollama)
- [x] Inline instrumentation at all 3 call sites: `LLMClient`, `LLMReranker`, `Answerer`
- [x] Streaming token extraction: Anthropic `stream.get_final_message()`, OpenAI `stream_options`
- [x] Admin API: `GET /admin/costs`, `GET /admin/costs/daily`, `GET /admin/stats`
- [x] Frontend Admin page: stat cards, provider breakdown, usage type breakdown, daily cost chart
- [x] Sidebar nav item under Tools
- [x] 20 tests (13 store + 7 API)

Deliverable: know exactly what LLM usage is costing you, broken down by provider, usage type, and day.

---

## Phase 6.5 — Quick Capture ✅
Goal: reduce friction for getting thoughts into the system from anywhere.

- [x] `POST /api/v1/capture` endpoint: accepts text, writes timestamped file to `Inbox/`
- [x] Minimal capture page at `/capture` in Next.js frontend: text box + submit button
- [x] Accessible via Tailscale from phone — no auth needed (Tailscale handles it)
- [x] Captured text processed by inbox processor on next hourly sync

Deliverable: any thought → into the system in under 10 seconds from your phone.

---

## Phase 7 — Weekly Review Generation ✅
Goal: automatic logbook that compounds value over time.

- [x] Post-sync job (runs Sundays, or on-demand via `make weekly-review`)
- [x] Reads the week's daily notes, extracts: Focus items, completed tasks, open tasks, recurring topics
- [x] Generates a weekly summary note in `00_Weekly/YYYY-WNN.md`
- [x] Pure template assembly (no LLM needed)
- [x] Indexed and searchable like any other note

Deliverable: in 6 months, look back at any week and see what happened.

---

## Phase 7.5 — Calendar Events ✅
Goal: the calendar shows your actual life, not just tasks.

- [x] Inbox classification: add `"event"` type with `event_date`, `event_time`, `event_end_date` fields
- [x] Event routing: store events in daily notes under `## Events` section
- [x] Event parser: read `## Events` from daily notes (same pattern as task aggregator)
- [x] API endpoint: `GET /api/v1/events?start=...&end=...`
- [x] Frontend: timed event cards in day sections (above tasks), multi-day banners spanning the week view

Deliverable: dictate "mom visiting at 10:30 tomorrow" and see it on your calendar.

See `docs/features/calendar-events.md` for full spec.

---

## Phase 8 — Task Management UI ✅
Goal: manage tasks from the browser without opening Obsidian.

- [x] Task update API: `PATCH /api/v1/tasks/update` writes status + due date changes directly to daily notes
- [x] Three-value status model: open (`- [ ]`), in-progress (`- [/]`), done (`- [x]`) throughout aggregator + API + frontend
- [x] Task detail panel: click task to see details, change status, change due date via date picker
- [x] Quick checkbox toggle on task rows (Tasks page + Calendar page)
- [x] Cache invalidation on write

Deliverable: check off tasks, change due dates, and track in-progress work from your phone.

See `docs/features/task-management-ui.md` for full spec.

---

## Phase 9 — Voice Chat via OpenAI Realtime API (~2-3 weeks)
Goal: hands-free voice interaction with the knowledge base using speech-to-speech.

- [ ] Backend WebSocket relay (`/api/v1/voice`) proxying audio to OpenAI Realtime API
- [ ] `gpt-realtime-mini` model (cost-efficient, strong tool calling)
- [ ] Tool call interception: `search_knowledge_base` calls existing RAG pipeline
- [ ] Frontend audio capture/playback via AudioWorklet + Web Audio API (Mac + iPhone)
- [ ] User interrupt / barge-in with response state machine
- [ ] Microphone button in chat UI (opt-in, text input remains default)
- [ ] Server VAD for natural turn-taking
- [ ] JSONL event logging + feature flag (default off)

Deliverable: talk to your vault hands-free from any device.

See `docs/features/voice-chat-realtime-api.md` for full spec.

---

## Phase 10 — Knowledge graph (V2, 4–8+ weeks)
- [ ] Choose graph store (Neo4j or Postgres)
- [ ] Entity resolution + dedupe
- [ ] Relationship extraction (LLM-assisted, human-reviewed)
- [ ] Graph exploration UI

Deliverable: true navigable concept graph, beyond similarity search.

---

## Phase 11 — Write-back workflow (V2+)
- [ ] PR-style changesets
- [ ] Apply suggested links/tags to Markdown files
- [ ] Versioning + rollback

Deliverable: assistant can help maintain your vault structure safely.

---

## Deferred (revisit when relevant)

Features that were planned but deprioritized based on current usage patterns and vault size.

- **Retrieval transparency** — Score breakdowns and "why this result" UI. Context-aware recency is already partially implemented (note dates passed to reranker/answerer). Full spec in `docs/features/retrieval-transparency.md`. Revisit when users report confusion about search results.
- **Proactive signals v1 (full version)** — Recurrence signals, signal schema, dismiss/snooze, full pipeline. Morning briefing (Phase 5) absorbs the core escalation value. Full spec in `docs/features/proactive-signals-v1.md`. Revisit after morning briefing ships and we learn what patterns actually surface.
- **Vault health checks** — Duplicate detection, folder size warnings, consolidation suggestions. Premature with ~16 notes. See deferred item in `docs/features/inbox-upgrade-anthropic-migration.md`.

---

## Future explorations (not committed)
These ideas have potential but need separate feasibility assessments before entering the roadmap.

- **Email ingestion (read-only)** — See `docs/features/EXPLORATION-email-ingestion.md`
- **Calendar integration (read-only)** — See `docs/features/EXPLORATION-calendar-integration.md`
- **Daily digest** — Trivial once morning briefing ships; could be a push notification or email summary
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
