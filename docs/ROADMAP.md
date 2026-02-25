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
| **Email ingestion: Gmail API direct, no MCP (2026-02-14)** | All existing Gmail MCP servers require write scopes; documented supply-chain attacks on MCP registries. Direct Gmail API with `gmail.readonly` is safer and simpler. Server-side query exclusions + Haiku `skip` classification control volume (replaces strict allowlist — too restrictive for new recruiters and unknown senders). Summary notes (not raw email) enter vault. Sandboxed LLM classification with spotlighting mitigates prompt injection. Cost: ~$1/month. See `docs/features/email-ingestion.md`. |
| **Email ingestion deprioritized to Phase 10 (2026-02-15)** | Quick capture already covers the "email → SecondBrain" workflow manually. Phases 8.5–9.5 deliver more tangible daily value. Email integration is a nice-to-have, not a daily pain point. Spec is ready to build whenever the signal is there ("I keep wishing that email had been in SecondBrain"). |
| **Deferred vault health checks** | Premature with ~16 notes. Note matching during inbox processing prevents the duplication that would make health checks necessary. Revisit at 100+ notes. |
| **Inbox upgrade: resolve open questions** | Note matching restricted to `10_Notes/` and `30_Concepts/` only (not projects). Frontend toggle labeled "Claude" (specific, recognizable). See `docs/features/inbox-upgrade-anthropic-migration.md`. |
| **Configurable categories over hardcoded constants (2026-02-15)** | Categories (AT&T, PwC, Personal) and subcategories are hardcoded Python constants. New users must edit source code. Moving to `data/settings.json` + Settings API + Settings UI makes SecondBrain adoptable by anyone. No automatic recategorization on change — users can already reassign per-task in the TaskDetailPanel. Defaults: "Work" + "Personal". See `docs/features/configurable-categories-ui.md`. |
| **Public demo instance for portfolio (2026-02-15)** | No way to showcase SecondBrain without exposing personal vault data. Deploy to Fly.io with fictional sample vault, rate limiting, and auto-deploy from main. ~$10-15/month. See `docs/features/public-demo-instance.md`. |
| **LLM observability: extend SQLite, defer Langfuse (2026-02-24)** | Built custom tracing (4 new columns on `llm_usage`, trace correlation, anomaly detection, Traces tab in admin dashboard). Chose this over LangSmith (cloud = privacy violation), OpenTelemetry (needs collector + backend), and Langfuse self-hosted (Docker + Postgres + second UI — overkill for v1). Langfuse is the documented upgrade path if the custom UI proves insufficient to maintain. See `docs/features/llm-observability-tracing.md`. |

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

## Phase 6.7 — LLM Observability & Tracing ✅
Goal: full visibility into what every LLM call does, how long it takes, how much it costs, and whether that's normal.

- [x] Enhanced schema: `trace_id`, `latency_ms`, `status`, `error_message` columns on `llm_usage`
- [x] All 4 LLM call sites instrumented with per-call timing, trace correlation, error/fallback tracking
- [x] Critical fix: LLMClient logs every provider attempt (failed Anthropic + successful Ollama = 2 rows)
- [x] Pricing guardrails: `calculate_cost()` warns on unknown paid models instead of silently returning $0
- [x] Anomaly detection: cost spike, call count spike, high error rate, high fallback rate (SQL-based, 3x multiplier)
- [x] API: `GET /admin/traces` (filtered list), `GET /admin/traces/{trace_id}` (correlated calls)
- [x] Frontend: Traces tab with filter dropdowns, expandable rows, trace group detail view, anomaly alert banners
- [x] Background batch health: `extraction_batch` and `inbox_batch` summary records in usage.db

Deliverable: the $300/month invisible extraction bug would have been caught in < 1 day with this in place.

See `docs/features/llm-observability-tracing.md` for full spec.

**Upgrade path:** If the custom tracing UI proves insufficient, migrate to self-hosted Langfuse (Docker + Postgres). Langfuse provides a mature trace waterfall, prompt versioning, eval scoring, and a dedicated UI — but adds infrastructure. Exhaust the simple approach first.

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

## Phase 8.5 — Calendar Week Grid ✅
Goal: see your whole week at a glance on desktop; navigate days instantly on mobile.

- [x] Fix mobile task text truncation (wrap instead of ellipsis on Tasks page)
- [x] Desktop multi-column grid: 1 column per day, all visible without scrolling
- [x] 5-day / 7-day toggle (smart default: 5d weekdays, 7d weekends)
- [x] Mobile day-picker ribbon: 7 day buttons with event/task count badges
- [x] Mobile single-day detail view with tap-to-select navigation
- [x] Responsive breakpoint orchestration (`md` = 768px)

Deliverable: glance at your week on desktop, tap through days on mobile.

See `docs/features/calendar-week-grid.md` for full spec.

---

## Phase 8.6 — Server Hardening ✅
Goal: eliminate silent failures from misconfigured server.

- [x] Make `.env` and `data_path` resolve from absolute paths (not cwd-dependent)
- [x] Add startup configuration logging (vault_path, data_path)
- [x] Replace silent empty API returns with HTTP 503 when vault missing
- [x] Remove redundant `Path("data")` fallbacks

Deliverable: misconfigured server fails loudly instead of returning empty data.

See `docs/features/server-hardening.md` for full spec.

---

## Phase 8.7 — Operational Hardening ✅
Goal: reliability, monitoring, and defensive infrastructure for sustained daily use.

- [x] Backend API launchd service (auto-start, auto-restart, correct cwd)
- [x] Meaningful health endpoint (vault, disk space, sync freshness)
- [x] Missing database indexes (conversation, index_tracker)
- [x] Daily sync completion marker
- [x] Log rotation (10MB threshold, keep 1 rotated copy)
- [x] Tighten exception handlers (specific exceptions, not blanket `Exception`)
- [x] Reindex lock (prevent double-reindex)
- [x] WAL checkpoint + synchronous=NORMAL tuning
- [x] Backup/restore Makefile commands
- [x] CORS middleware (defensive, localhost-only)
- [x] Structured logging for critical sync events
- [x] Sync status indicator in admin UI

Deliverable: system that restarts itself, logs meaningfully, and fails loudly.

See `docs/features/operational-hardening.md` for full spec.

---

## Phase 8.8 — Configurable Categories UI ✅
Goal: make task categories and subcategories user-configurable via the UI instead of hardcoded Python constants.

- [x] Settings file (`data/settings.json`) with reader/writer and sensible defaults ("Work" + "Personal")
- [x] Settings API: `GET/PUT /api/v1/settings/categories`
- [x] Inbox processor reads categories from settings file (dynamic prompt building)
- [x] Settings UI page with category/subcategory CRUD (add, edit, delete)
- [x] Update frontend branding defaults to generic ("SecondBrain" instead of "Brent OS")

Deliverable: new user clones repo, opens settings page, configures their categories — no code editing required.

See `docs/features/configurable-categories-ui.md` for full spec.

---

## Phase 8.9 — Public Demo Instance (~4-5 days, ~$10-15/month)
Goal: interactive demo with sample data that anyone can try from the README, without exposing personal vault data.

- [ ] Sample vault with fictional persona ("Alex Chen") — daily notes, tasks, projects, concepts
- [ ] Dockerfile (multi-stage: frontend build + backend + sample vault)
- [ ] Rate limiting middleware (gated by `DEMO_MODE` env var)
- [ ] GitHub Actions deploy pipeline → Fly.io (auto-deploy on push to main)
- [ ] README badge and demo link

Deliverable: visitors click "Live Demo" in README and interact with a fully functional SecondBrain using sample data.

See `docs/features/public-demo-instance.md` for full spec.

---

## Phase 9 — Smarter Retrieval (~2-3 days)
Goal: make the RAG pipeline and capture flow aware of your vault's link structure.

- [ ] Wiki link parser: extract `[[wiki links]]` from markdown text (handles aliases, headings, code block exclusion)
- [ ] Link resolver: title → note_path lookup via LexicalStore (case-insensitive)
- [ ] Link expander: after reranking, follow 1-hop wiki links from top candidates, inject up to 3 linked chunks as supplementary context for the answerer
- [ ] Capture connections: after writing to Inbox, run hybrid retrieval on captured text, return top 5 related notes in the API response (no LLM reranking — raw scores only)
- [ ] Metadata-enriched snippets: use extracted summaries as connection snippets when available
- [ ] Frontend connection cards: show related notes below the success message on the Capture page

Deliverable: chat answers incorporate context from linked notes; captures immediately show what's related in your vault.

See `docs/features/link-aware-retrieval.md` and `docs/features/capture-connection-surfacing.md` for full specs.
Implementation prompt: `docs/features/PROMPT-link-retrieval-and-capture-connections.md`

---

## Phase 9.5 — Insights Dashboard (~3-5 days)
Goal: bring the placeholder Insights page to life using the existing backend APIs.

- [ ] Note explorer: pick a note → see summary, entities, dates, action items, related notes, suggested links
- [ ] Entity browser: vault-wide entity list filterable by type (person, org, product, place), click to see which notes mention them
- [ ] Vault stats: total indexed notes, entity counts by type, most-connected notes (most incoming suggestions)
- [ ] Wiki link map (post-Phase 9): for a selected note, show its outgoing `[[wiki links]]` and which notes link back to it

Deliverable: browse your vault's knowledge structure — entities, connections, and metadata — without opening Obsidian.

Note: All backend APIs already exist (`/metadata`, `/suggestions`, `/entities`, `/action-items`). This phase is purely frontend.

---

## Phase 10 — Email Ingestion (Read-Only) (~5-7 days)
Goal: bring email context into SecondBrain without compromising vault signal-to-noise or security.

- [ ] Gmail API client with `gmail.readonly` OAuth scope (direct API, no MCP)
- [ ] Email pre-filter + sanitizer (server-side query exclusions + optional sender blocklist, text-only extraction, hidden char stripping)
- [ ] Sandboxed LLM classification with spotlighting (Haiku `skip` category filters remaining noise)
- [ ] Vault note writer (summary notes to `40_Email/`, deduplication by message ID)
- [ ] Daily sync integration (new stage, gated by `email_enabled` config flag)
- [ ] Configuration (env vars for query filter, blocklist, max per sync)

Deliverable: emails from your Primary inbox appear as searchable summary notes in your vault. New recruiters, appointment reminders, and family emails flow through automatically; noise is excluded by Gmail query filters and Haiku classification.

See `docs/features/email-ingestion.md` for full spec.
Implementation prompt: `docs/features/PROMPT-email-ingestion.md`

---

## Phase 11 — Voice Chat via OpenAI Realtime API (~2-3 weeks)
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

## Phase 12 — Knowledge graph (V2, 4–8+ weeks)
- [ ] Choose graph store (Neo4j or Postgres)
- [ ] Entity resolution + dedupe
- [ ] Relationship extraction (LLM-assisted, human-reviewed)
- [ ] Graph exploration UI

Deliverable: true navigable concept graph, beyond similarity search.

---

## Phase 13 — Write-back workflow (V2+)
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
- **Langfuse migration (self-hosted)** — Replace custom tracing UI with Langfuse (`docker compose up`, Python SDK `@observe` decorator on 4 call sites). Provides mature trace waterfall, prompt versioning, eval scoring, session tracking. Trade-off: adds Docker + Postgres infrastructure. Revisit if: (1) the built-in Traces tab is too limited for debugging, (2) we want prompt versioning or LLM evals, or (3) maintaining the custom tracing code becomes a burden vs. using an actively developed OSS tool. See `docs/features/llm-observability-tracing.md` architecture decision table.

---

## Future explorations (not committed)
These ideas have potential but need separate feasibility assessments before entering the roadmap.

- **Email ingestion (read-only)** — Assessed and promoted to Phase 10. See `docs/features/email-ingestion.md`
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
