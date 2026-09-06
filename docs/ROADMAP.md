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
TRACE-1 (OTel export) ◄── done
  └─► TRACE-2 (Langfuse) ◄── done
        └─► TRACE-3 (Full platform) ◄── done (covered by OTel architecture)

OPS-3 (Cloud migration) ─► OPS-2 (Public demo)
OPS-3 (Cloud migration) ─► EMAIL-1 (Gmail ingestion)

ENGAGE-1 (Today surface + daily push plumbing) ◄── done
  ├─► ENGAGE-2 (Resurfacing: spaced-repetition + on-this-day)
  ├─► ENGAGE-3 (Related-notes panel — absorbs RETRIEVAL-2)
  └─► FEED-1 (RSS attention router: AI + sports) ◄── done
        ├─► FEED-2 (Engagement learning + save-to-vault via KLIB-1)
        ├─► FEED-3 (Google Calendar read-only)
        └─► FEED-4 (Gmail — absorbs EMAIL-1)
              └─► FEED-5 (Podcasts / X — deferred, expensive)

RETRIEVAL-1 (Wiki links) ◄── done
  └─► RETRIEVAL-2 (Capture connections) ── folded into ENGAGE-3
RETRIEVAL-3 (Insights dashboard) — independent

EMAIL-1 (Gmail ingestion) — depends on OPS-3

VOICE-1 (Realtime API) — independent

KG-1 (Knowledge graph) — independent
WRITEBACK-1 (Changeset workflow) — depends on KG-1

KLIB-1 (External content ingestion) ◄── done
KLIB-2 (Vault lint/health checks) — independent
KLIB-3 (Compounding query loop) ◄── done
```

---

---

## Epic: ENGAGE — Proactive Resurfacing & Daily Habit

> **Top priority.** The tool "works well" but pull-only tools don't build habits. ENGAGE adds a changing daily surface and a local push so there's a reason to open SecondBrain every day — powered by infrastructure already built (briefing, task aggregation, hybrid search, daily-sync cron). All mechanics are local-first and suggestion-only. No gamification (single-user tool: any mechanic that isn't genuine value is self-sabotage).

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| ENGAGE-2 | Resurfacing block: spaced-repetition (SM-2, schedule in frontmatter) + "on this day" temporal | 2-3d | Backlog | — |
| ENGAGE-3 | Related-notes panel (in-context; absorbs RETRIEVAL-2 capture connections) | 1-2d | Backlog | [spec](features/capture-connection-surfacing.md) |

_ENGAGE-1 delivered — see [DELIVERED.md](DELIVERED.md)._

---

## Epic: FEED — Personalized Attention Router

> Bring the *outside world* onto the same daily surface: a cheap, personalized content feed (AI space + sports) that learns from engagement. Cost is a hard design constraint — filter with heuristics before spending on LLM, one batched summary call/day (~$0.15/mo), no embeddings in the trial, aggressive pruning, local models for grunt work. Trial narrow (RSS-only), expand only if the habit sticks.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| FEED-2 | Engagement learning (click/thumbs → interest-weight tuning) + "save to vault" via KLIB-1 | 2d | Backlog | — |
| FEED-3 | Google Calendar read-only → real events in the daily brief | 1-2d | Backlog | [exploration](features/EXPLORATION-calendar-integration.md) |
| FEED-4 | Gmail read-only (absorbs EMAIL-1): trusted-sender summaries, recruiter/family detection, newsletter ingestion | 5-7d | Backlog | [spec](features/email-ingestion.md) |
| FEED-5 | Podcasts (captions) / X — deferred until the cheaper feed proves the habit; expensive sources | TBD | Backlog | — |

---

## Epic: Operations & Infrastructure

> Reliability, monitoring, and deployment infrastructure.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| OPS-3 | Cloud migration (containerize API + workers, deploy to Railway/Fly.io, isolate content ingestion) | 3-4d | **Pending** | — |
| OPS-2 | Public demo instance (Fly.io, sample vault, rate limiting) | 4-5d | **Pending** | [spec](features/public-demo-instance.md) |

---

## Epic: Smarter Retrieval & Discovery

> Make the RAG pipeline and frontend aware of vault structure, links, and metadata.

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| RETRIEVAL-2 | Capture connections (related notes surfaced after quick capture) — **moved to ENGAGE-3** | 1-2d | Backlog | [spec](features/capture-connection-surfacing.md) |
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
| KLIB-2 | Vault lint & health checks (contradiction detection, orphan pages, stale content, coverage gaps) | 2-3d | Backlog | — |
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
| **OTel traces complement UsageStore** | Different purposes: UsageStore = cost/anomaly dashboard, OTel = behavioral evals and observability. |
| **Voice chat: resolve v1 decisions** | Single voice (alloy), fresh sessions, server VAD only, no Whisper fallback. |
| **Configurable categories over hardcoded** | New users shouldn't need to edit source code. |
| **Recency via LLM context, not decay formula** | When two similar notes exist, the LLM contextually prefers the recent one during synthesis. |
| **Knowledge Library: hybrid with RAG, not replacement** | Karpathy's LLM Wiki (compile-then-query) is complementary to SecondBrain's RAG (index-then-retrieve). Wiki pages become vault content indexed by the existing pipeline. Progressive disclosure pattern: wiki index = metadata layer, RAG = deep retrieval. |
| **Cloud migration before OPS-2 and EMAIL-1** | External content ingestion (KLIB-1) is safe enough locally — text-only extraction, no code execution, safety auditor gates all content. But public demo and email ingestion need proper isolation. OPS-3 added as prerequisite. |
| **Safety auditor uses Sonnet (latest)** | Stronger model for security-critical classification. Cost is ~$0.01-0.02 per document — negligible for the ingestion volume. Three-layer hardening: XML delimiters, structured output, tool message pattern. |
| **Retention is the real gap, not capability** | Tool "works well" but usage dropped. Root cause: pull-only tools don't build habits. ENGAGE + FEED prioritized over Voice/KG/Write-back, which add power without adding a reason to open the app. |
| **No gamification (single-user)** | Maker and user are the same person. Streaks, guilt-nudges, and fake variable rewards farm your own attention — self-sabotage. Only genuine-value ("Facilitator quadrant") mechanics: changing surface, real serendipity, useful push. |
| **FEED cost discipline** | Filter with free heuristics (source trust × keyword × interest weight) before any LLM. One batched summary call/day (~$0.15/mo). No embeddings in trial; local BGE/Ollama for dedup/scoring if needed. Prune feed rows after 30d. |
| **Defer X/Twitter and podcast transcription** | X API ~$200/mo and Nitter is dead; Whisper transcription is the expensive part of podcasts. Most AI voices cross-post to free-RSS newsletters/blogs; Gmail-as-universal-inbox (EMAIL-1) ingests the rest. Revisit only if the cheap feed proves the habit. |
| **ENGAGE + FEED share one push surface** | Interleave build: ship the "Today" surface + local daily push once (ENGAGE-1), then land resurfacing (ENGAGE-2) and the RSS feed (FEED-1) onto it. Two feeds — inward (notes) and outward (world) — one delivery channel. |
