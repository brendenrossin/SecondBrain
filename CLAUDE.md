# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SecondBrain is a semantic memory system built on top of an Obsidian vault. It combines Markdown note ingestion, embeddings, hybrid search (BM25 + vectors), and optional knowledge graphs to enable intelligent retrieval and synthesis from personal notes.

**Key principle:** Local-first by default with optional secure remote access via VPN/tunneling. No public internet exposure in POC phase.

## Current Status

This repository has completed **Phase 0** (scaffolding) and is ready for Phase 1 implementation.

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
make clean     # Remove build artifacts
```

## Environment Variables

```bash
SECONDBRAIN_VAULT_PATH=/path/to/obsidian/vault  # Required for indexing
SECONDBRAIN_HOST=127.0.0.1                       # API server host
SECONDBRAIN_PORT=8000                            # API server port
SECONDBRAIN_GRADIO_PORT=7860                     # Gradio UI port
SECONDBRAIN_DATA_PATH=data                       # Data storage directory
OPENAI_API_KEY=sk-...                            # Required for LLM features
```

## Project Structure

```
src/secondbrain/
├── main.py              # FastAPI app entry point
├── config.py            # Settings (pydantic-settings)
├── models.py            # Pydantic models
├── ui.py                # Gradio UI
├── vault/               # Vault connector + parser
├── indexing/            # Chunker + embedder
├── stores/              # Vector (ChromaDB), lexical (FTS5), conversation
├── retrieval/           # Hybrid search + reranker
├── synthesis/           # LLM answer generation
├── api/                 # FastAPI routes (/ask, /index)
└── logging/             # Query logger (JSONL)
```

## Architecture

### Core Components
1. **Vault Connector** - Reads Markdown + frontmatter from Obsidian vault
2. **Indexer** - Markdown-aware chunker, embedding generator, BM25 builder
3. **Stores** - Document store (SQLite/Postgres), vector store (pgvector/Qdrant/Chroma), lexical store (BM25)
4. **Retrieval Service** - Hybrid search + reranking + citation assembly
5. **Answer Service** - Optional LLM synthesis with strict grounding

### Tech Stack (Planned)
- **Language:** Python + FastAPI
- **Documents:** SQLite (POC) → Postgres (V1+)
- **Vectors:** Chroma or Qdrant (local)
- **Lexical Search:** SQLite FTS5 (POC) → Meilisearch (V1+)
- **Embeddings:** sentence-transformers (local)
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
2. `docs/ROADMAP.md` - Phased implementation plan (Phase 0-7)
3. `docs/SOLUTION_ARCHITECTURE.md` - Tech choices and rationale
4. `docs/DATA_MODEL.md` - Schema, entities, relations
5. `docs/INDEXING_PIPELINE.md` - Chunking and embedding details
6. `docs/API_SPEC.md` - REST endpoint specifications
7. `docs/SECURITY_PRIVACY.md` - Threat model and hardening
8. `docs/OPERATIONS_OBSERVABILITY.md` - Logging, metrics, backups

## Implementation Phases

- **Phase 0:** Repo scaffolding, CI/CD, config system, Makefile
- **Phase 1:** POC indexing + retrieval (vault ingestion, chunker, hybrid search)
- **Phase 2:** Quality improvements (incremental re-indexing, reranking, caching)
- **Phase 3:** Metadata extraction + suggestions
- **Phase 4:** Secure remote access (VPN/tunnel + auth)
- **Phase 5:** Chat interface (optional)
- **Phase 6:** Knowledge graph (V2)
- **Phase 7:** Write-back workflow (V2+)

## Security Requirements

- Bind services to `127.0.0.1` by default
- Passkeys/WebAuthn for web UI auth
- TLS everywhere for remote access
- OS keychain for secrets (never commit .env)
- Never auto-edit notes without user approval (changeset workflow)
- Vault remains the source of truth
