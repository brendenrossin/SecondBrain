# Roadmap

Active work for SecondBrain, organized by epic. Each epic contains individual tickets that flow through statuses. When a ticket's PR is merged, it moves to [DELIVERED.md](DELIVERED.md).

## Guiding Principles

- Ship in thin vertical slices: Ingest → index → retrieve → cite → synthesize
- Vault is the single source of truth — no state outside it
- Suggestion-only: the system recommends, never acts
- Simple, maintainable systems over clever or fragile ones
- Local-first, privacy-preserving

## Ticket Statuses

| Status | Meaning |
|--------|---------|
| **Backlog** | Defined but not prioritized for near-term work |
| **Pending** | Prioritized, ready to pick up |
| **In Progress** | Active development |
| **Review** | Implementation complete, running `/tri-review` |
| **PR** | PR created, awaiting merge |

Once a PR merges → ticket moves to `DELIVERED.md` with date and PR link.

---

## Dependency Tree

Arrows mean "must complete before." Items without dependencies can be worked in any order.

```
TRACE-1 (OTel export)
  └─► TRACE-2 (Langfuse) ─► TRACE-3 (Full platform)

OPS-1 (Log persistence) — independent
OPS-2 (Public demo) — independent

RETRIEVAL-1 (Wiki links) ◄── done
  └─► RETRIEVAL-2 (Capture connections)
RETRIEVAL-3 (Insights dashboard) — independent

EMAIL-1 (Gmail ingestion) — independent

VOICE-1 (Realtime API) — independent

KG-1 (Knowledge graph) — independent
WRITEBACK-1 (Changeset workflow) — depends on KG-1

KLIB-1 (External content ingestion) — independent
KLIB-2 (Vault lint/health checks) — independent
KLIB-3 (Compounding query loop) — independent
```

---

## Epic: LLM Tracing & Evaluation

> Instrument LLM calls with OTel, export traces for TraceEval, evolve toward hosted trace platform.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| TRACE-2 | Langfuse free tier integration (trace viewer UI) | 2-3d | Backlog | — |
| TRACE-3 | Full platform (LangSmith/Arize, only if warranted) | TBD | Backlog | — |

---

---

## Epic: Operations & Infrastructure

> Reliability, monitoring, and deployment infrastructure.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| OPS-1 | Log persistence & data retention (launchd logs, usage pruning) | 1d | Backlog | [spec](features/log-persistence-retention.md) |
| OPS-2 | Public demo instance (Fly.io, sample vault, rate limiting) | 4-5d | **Pending** | [spec](features/public-demo-instance.md) |

---

## Epic: Smarter Retrieval & Discovery

> Make the RAG pipeline and frontend aware of vault structure, links, and metadata.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| RETRIEVAL-2 | Capture connections (related notes surfaced after quick capture) | 1-2d | Backlog | [spec](features/capture-connection-surfacing.md) |
| RETRIEVAL-3 | Insights dashboard (note explorer, entity browser, vault stats) | 3-5d | Backlog | — |

---

## Epic: Email Ingestion

> Bring email context into SecondBrain (read-only) without compromising vault signal-to-noise.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| EMAIL-1 | Gmail API read-only ingestion (classify, summarize, route to vault) | 5-7d | Backlog | [spec](features/email-ingestion.md) |

---

## Epic: Voice Chat

> Hands-free voice interaction with the knowledge base using speech-to-speech.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| VOICE-1 | OpenAI Realtime API integration (WebSocket relay, tool calls, audio UI) | 2-3w | Backlog | [spec](features/voice-chat-realtime-api.md) |

---

## Epic: Knowledge Graph (V2)

> True navigable concept graph, beyond similarity search.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| KG-1 | Graph store + entity resolution + relationship extraction + UI | 4-8w | Backlog | — |

---

## Epic: Write-Back Workflow (V2+)

> Assistant can help maintain vault structure safely via PR-style changesets.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| WRITEBACK-1 | Changeset workflow (apply suggested links/tags, versioning, rollback) | TBD | Backlog | — |

---

## Epic: Knowledge Library (Karpathy-style)

> LLM-compiled knowledge base from external sources — articles, papers, web clips ingested into structured wiki pages. Inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) pattern (compile-then-query), layered on top of SecondBrain's existing RAG infrastructure.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| KLIB-1 | External content ingestion (drop URL/file in Quick Capture → safety audit → fetch → LLM compile → wiki page → index) | 3-5d | **Pending** | — |
| KLIB-2 | Vault lint & health checks (contradiction detection, orphan pages, stale content, coverage gaps) | 2-3d | Backlog | — |
| KLIB-3 | Compounding query loop (save valuable synthesis answers back as wiki pages) | 1-2d | **Pending** | — |
| KLIB-4 | AI-powered research mode (search topic → compile findings → ingest as wiki pages) | TBD | Backlog | — |

---

## Deferred (revisit when relevant)

Features deprioritized based on current usage patterns and vault size.

- **Retrieval transparency** — Score breakdowns and "why this result" UI. Revisit when users report confusion about search results. See `docs/features/retrieval-transparency.md`.
- **Proactive signals v1** — Recurrence signals, signal schema, dismiss/snooze. Morning briefing absorbs the core escalation value. See `docs/features/proactive-signals-v1.md`.
- **Vault health checks** — Duplicate detection, folder size warnings. Premature with ~16 notes. Revisit at 100+ notes.

---

## Decisions Log

| Decision | Rationale |
|----------|-----------|
| **Cut Task lifecycle engine** | Source-of-truth conflict with vault-driven architecture. Current heuristics cover the need. See `docs/features/DEFERRED-task-lifecycle.md`. |
| **Deprecated Gradio UI** | Next.js frontend is the sole UI. |
| **Vault stays authoritative** | No application state outside the vault and its derived indexes. |
| **Email: Gmail API direct, no MCP** | MCP servers require write scopes; supply-chain risk. Direct `gmail.readonly` is safer. |
| **Email deprioritized** | Quick capture covers the manual workflow. Spec is ready when the need is clear. |
| **LLM observability: SQLite first, defer Langfuse** | Custom tracing (trace_id, latency, status, anomaly detection) is sufficient for v1. Langfuse is the upgrade path. |
| **OTel traces complement UsageStore** | Different purposes: UsageStore = cost/anomaly dashboard, OTel = TraceEval behavioral evals. |
| **Voice chat: resolve v1 decisions** | Single voice (alloy), fresh sessions, server VAD only, no Whisper fallback. |
| **Configurable categories over hardcoded** | New users shouldn't need to edit source code. |
| **Recency via LLM context, not decay formula** | When two similar notes exist, the LLM contextually prefers the recent one during synthesis. |
| **Knowledge Library: hybrid with RAG, not replacement** | Karpathy's LLM Wiki (compile-then-query) is complementary to SecondBrain's RAG (index-then-retrieve). Wiki pages become vault content indexed by the existing pipeline. Progressive disclosure pattern: wiki index = metadata layer, RAG = deep retrieval. |
