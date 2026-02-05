# Obsidian Semantic Memory + Knowledge Graph Assistant

This repo is a product + architecture starter kit for building a **secure, personal semantic memory system** on top of an Obsidian vault.

## What you get (docs)
- `docs/PRD.md` — product requirements (POC → v1 → v2)
- `docs/SOLUTION_ARCHITECTURE.md` — end-to-end architecture options
- `docs/ROADMAP.md` — milestones, sequencing, scope control
- `docs/SECURITY_PRIVACY.md` — threat model, encryption, auth, secrets
- `docs/DATA_MODEL.md` — note schema, entities/relations, KG model
- `docs/INDEXING_PIPELINE.md` — chunking/embeddings/hybrid search
- `docs/API_SPEC.md` — API endpoints + bot/web clients
- `docs/OPERATIONS_OBSERVABILITY.md` — logging, tracing, backups, SLOs

## Core idea
- **Source of truth:** Obsidian Markdown files (vault on Mac Studio)
- **Processing:** ingestion + chunking + embeddings + metadata extraction
- **Retrieval:** hybrid search (BM25 + vectors) + optional knowledge graph
- **Interfaces:** local UI + secure remote access (web + chat bots)
- **Security:** local-first by default; remote access is opt-in and hardened

## Quick start

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Setup
```bash
# Install dependencies
make install

# Run the development server
make dev

# Verify it's working
curl http://localhost:8000/health
# Returns: {"status": "ok"}
```

### Development commands
```bash
make dev       # Run dev server with hot reload
make test      # Run tests
make lint      # Run linter
make format    # Format code
make typecheck # Run type checker
make check     # Run all checks (lint + typecheck + test)
```

## Documentation
1. Read `docs/PRD.md` and `docs/ROADMAP.md`
2. Pick a deployment mode in `docs/SOLUTION_ARCHITECTURE.md`
3. Implement the POC pipeline in `docs/INDEXING_PIPELINE.md`
4. Add an interface (web or chat bot) per `docs/API_SPEC.md`

> Tip: Keep the POC brutally small: one vault, one embedding model, one vector store, and a read-only query UI.
