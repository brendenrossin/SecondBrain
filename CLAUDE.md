# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SecondBrain is a semantic memory system built on top of an Obsidian vault. It combines Markdown note ingestion, embeddings, hybrid search (BM25 + vectors), and optional knowledge graphs to enable intelligent retrieval and synthesis from personal notes.

**Key principles:**
- Local-first, privacy-preserving
- Vault is the single source of truth — no application state outside it
- Suggestion-only: the system recommends, never acts autonomously
- Simple, maintainable systems over clever or fragile ones

## Current Status

Phases 0–4 are complete. The system has vault ingestion, chunking, hybrid search (BM25 + vectors), LLM reranking, answer synthesis, metadata extraction, a Next.js frontend ("Mission Control" dashboard), task aggregation with bi-directional vault sync, and secure remote access via Tailscale. The Gradio UI is deprecated.

## Build & Development Commands

```bash
make install   # Install dependencies with uv
make dev       # Run FastAPI server at http://localhost:8000
make ui        # Run Gradio UI at http://localhost:7860
make index     # Trigger vault indexing via API
make test      # Run pytest
make lint      # Run ruff linter
make format    # Run ruff formatter
make typecheck # Run mypy type checker
make check     # Run all checks (lint + typecheck + test)
make eval      # Run RAG evaluation harness
make reindex   # Reindex vault standalone (no server needed)
make daily-sync # Run full daily sync (inbox + tasks + reindex)
make clean     # Remove build artifacts
```

## Environment Variables

```bash
SECONDBRAIN_VAULT_PATH=/path/to/obsidian/vault        # Required for indexing
SECONDBRAIN_HOST=127.0.0.1                             # API server host
SECONDBRAIN_PORT=8000                                  # API server port
SECONDBRAIN_GRADIO_PORT=7860                           # Gradio UI port
SECONDBRAIN_DATA_PATH=data                             # Data storage directory
SECONDBRAIN_OPENAI_API_KEY=sk-...                      # Required for LLM features
SECONDBRAIN_EMBEDDING_PROVIDER=local                   # "local" or "openai"
SECONDBRAIN_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5     # Local embedding model
SECONDBRAIN_OPENAI_EMBEDDING_MODEL=text-embedding-3-small  # OpenAI embedding model
SECONDBRAIN_OPENAI_EMBEDDING_DIMENSIONS=               # Optional dimension override
```

## Project Structure

```
src/secondbrain/
├── main.py              # FastAPI app entry point
├── config.py            # Settings (pydantic-settings)
├── models.py            # Pydantic models
├── ui.py                # Gradio UI
├── vault/               # Vault connector + parser
├── indexing/            # Chunker + multi-provider embedder
├── stores/              # Vector (ChromaDB), lexical (FTS5), conversation
├── retrieval/           # Hybrid search + reranker
├── synthesis/           # LLM answer generation
├── eval/                # RAG evaluation harness + metrics
├── api/                 # FastAPI routes (/ask, /index)
├── scripts/             # Daily sync, inbox processor, task aggregator
└── logging/             # Query logger (JSONL)
```

## Architecture

### Core Components
1. **Vault Connector** - Reads Markdown + frontmatter from Obsidian vault
2. **Indexer** - Markdown-aware chunker, embedding generator, BM25 builder
3. **Stores** - Document store (SQLite/Postgres), vector store (pgvector/Qdrant/Chroma), lexical store (BM25)
4. **Retrieval Service** - Hybrid search + reranking + citation assembly
5. **Answer Service** - Optional LLM synthesis with strict grounding

### Tech Stack
- **Language:** Python + FastAPI
- **Documents:** SQLite (WAL mode)
- **Vectors:** ChromaDB (local)
- **Lexical Search:** SQLite FTS5
- **Embeddings:** BAAI/bge-base-en-v1.5 (default, local) or OpenAI text-embedding-3-small (API)
- **LLM:** OpenAI gpt-4o-mini (reranking + synthesis) or local Ollama
- **UI:** Next.js frontend (dark "mission control" dashboard). Gradio is deprecated.
- **Knowledge Graph:** Neo4j or Postgres (V2, optional)

### Data Flow
1. File change detected → parse Markdown → extract frontmatter/headings/blocks
2. Create stable chunk IDs using `hash(note_path + heading_path + block)`
3. Generate embeddings → store in vector DB
4. Build BM25/FTS lexical index
5. Query: hybrid retrieve (BM25 + vectors) → rerank → return with citations

## Documentation Structure

Read docs in this order for full context:
1. `docs/PRD.md` - Product requirements and vision
2. `docs/ROADMAP.md` - Phased implementation plan (Phase 0-8) + decisions log
3. `docs/SOLUTION_ARCHITECTURE.md` - Tech choices and rationale
4. `docs/DATA_MODEL.md` - Schema, entities, relations
5. `docs/INDEXING_PIPELINE.md` - Chunking and embedding details
6. `docs/API_SPEC.md` - REST endpoint specifications
7. `docs/SECURITY_PRIVACY.md` - Threat model and hardening
8. `docs/OPERATIONS_OBSERVABILITY.md` - Logging, metrics, backups
9. `docs/UI_DESIGN_SPEC.md` - Frontend redesign spec ("Mission Control" dashboard overhaul)
10. `docs/ENGINEERING_REVIEW.md` - System health assessment, improvement priorities, and review criteria for changes
11. `docs/features/*.md` - Individual feature specs, explorations, and deferred proposals

## Implementation Phases

- **Phase 0:** Repo scaffolding, CI/CD, config system, Makefile *(done)*
- **Phase 1:** POC indexing + retrieval (vault ingestion, chunker, hybrid search) *(done)*
- **Phase 2:** Quality improvements (incremental re-indexing, reranking, eval framework, embedding upgrade) *(done)*
- **Phase 3:** Metadata extraction + suggestions *(done)*
- **Phase 3.5:** Next.js frontend + UI redesign *(done)*
- **Phase 4:** Secure remote access (Tailscale) *(done)*
- **Phase 5:** Morning briefing dashboard *(done)*
- **Phase 5.5:** Inbox upgrade + Anthropic migration *(done)*
- **Phase 5.7:** User configurability *(done)*
- **Phase 6:** LLM cost tracking + admin dashboard *(done)*
- **Phase 6.5:** Quick capture
- **Phase 7:** Weekly review generation
- **Phase 8:** Voice chat via OpenAI Realtime API
- **Phase 9:** Knowledge graph (V2)
- **Phase 10:** Write-back workflow (V2+)

## Security Requirements

- Bind services to `127.0.0.1` by default
- Passkeys/WebAuthn for web UI auth
- TLS everywhere for remote access
- OS keychain for secrets (never commit .env)
- Never auto-edit notes without user approval (changeset workflow)
- Vault remains the source of truth
