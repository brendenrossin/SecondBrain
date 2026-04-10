# Delivered

Completed work, moved here after PR merge. Grouped by epic, ordered by completion date (newest first).

---

## Epic: LLM Observability & Tracing

| ID | Ticket | Completed | PR |
|----|--------|-----------|----|
| TRACE-1 | OpenLLMetry auto-instrumentation + JSONL file export (traceloop-sdk, FileSpanExporter, BatchSpanProcessor) | 2026-04-09 | [#4](https://github.com/brendenrossin/SecondBrain/pull/4) |
| OBS-1 | LLM observability & tracing — trace_id, latency, status, error tracking, anomaly detection, admin Traces tab | 2026-04-09 | [#2](https://github.com/brendenrossin/SecondBrain/pull/2) |

---

## Epic: Knowledge Library (Karpathy-style)

| ID | Ticket | Completed | PR |
|----|--------|-----------|----|
| KLIB-1 | External content ingestion (URL → safety audit → fetch → LLM compile → wiki page → index) | 2026-04-10 | [#7](https://github.com/brendenrossin/SecondBrain/pull/7) |
| KLIB-3 | Compounding query loop (save valuable synthesis answers back as wiki pages) | 2026-04-10 | [#7](https://github.com/brendenrossin/SecondBrain/pull/7) |

---

## Epic: RAG Quality & Performance

| ID | Ticket | Completed | PR |
|----|--------|-----------|----|
| RAG-3 | Topic manifest / knowledge-base summary — vault-level awareness for answerer grounding | 2026-04-10 | [#6](https://github.com/brendenrossin/SecondBrain/pull/6) |
| RAG-2 | Caching layer — embedding cache + IndexCache (skip unchanged chunks on reindex) | 2026-04-10 | [#6](https://github.com/brendenrossin/SecondBrain/pull/6) |
| RAG-1 | Contextual retrieval — LLM-generated chunk context blurbs at index time (Anthropic Haiku, progressive disclosure for RAG) | 2026-04-09 | [#5](https://github.com/brendenrossin/SecondBrain/pull/5) |

---

## Epic: RAG Reliability

| ID | Ticket | Completed | PR |
|----|--------|-----------|----|
| REL-1 | RAG reliability fixes — proxy timeout, reranker parsing, stream error handling, smart warmup, SSE safeguards | 2026-04-09 | [#3](https://github.com/brendenrossin/SecondBrain/pull/3) |

---

## Epic: Frontend & UI

| ID | Ticket | Completed | PR |
|----|--------|-----------|----|
| UI-7 | Configurable categories UI (settings page, dynamic prompt building) | 2026-02 | — |
| UI-6 | Calendar week grid (desktop multi-column, mobile day-picker) | 2026-02 | — |
| UI-5 | Task management UI (status toggle, due date picker, detail panel) | 2026-02 | — |
| UI-4 | Quick capture page | 2026-02 | — |
| UI-3 | LLM cost tracking + admin dashboard | 2026-02 | — |
| UI-2 | Calendar events (timed cards, multi-day banners) | 2026-02 | — |
| UI-1 | Next.js frontend + Mission Control redesign | 2026-01 | — |

---

## Epic: Daily Workflow

| ID | Ticket | Completed | PR |
|----|--------|-----------|----|
| DW-4 | Weekly review generation (template assembly, weekly summary notes) | 2026-02 | — |
| DW-3 | User configurability (branding config, clone-friendly setup) | 2026-02 | — |
| DW-2 | Inbox upgrade + Anthropic migration (Claude Sonnet, fallback chain, note matching) | 2026-02 | — |
| DW-1 | Morning briefing dashboard (overdue tasks, today's plan, aging follow-ups) | 2026-02 | — |

---

## Epic: Operations & Infrastructure

| ID | Ticket | Completed | PR |
|----|--------|-----------|----|
| OPS-4 | Operational hardening (launchd, health endpoint, WAL tuning, backup/restore) | 2026-02 | — |
| OPS-3 | Server hardening (absolute paths, startup logging, 503 on missing vault) | 2026-02 | — |

---

## Epic: Access & Security

| ID | Ticket | Completed | PR |
|----|--------|-----------|----|
| SEC-1 | Secure remote access via Tailscale | 2026-01 | — |

---

## Epic: Core Platform

| ID | Ticket | Completed | PR |
|----|--------|-----------|----|
| CORE-6 | Smarter retrieval — wiki link expansion (1-hop linked context for answerer) | 2026-03 | — |
| CORE-5 | Metadata extraction + suggestions (entities, dates, action items, related notes) | 2026-01 | — |
| CORE-4 | Quality improvements (incremental indexing, reranking, eval framework, BGE upgrade) | 2026-01 | — |
| CORE-3 | Lexical search (SQLite FTS5) | 2026-01 | — |
| CORE-2 | POC indexing + retrieval (vault ingestion, chunker, hybrid search, Gradio UI) | 2026-01 | — |
| CORE-1 | Repo scaffolding, CI/CD, config system, Makefile | 2026-01 | — |
