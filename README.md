# SecondBrain

A personal semantic memory system built on top of an Obsidian vault. Combines Markdown note ingestion, embeddings, hybrid search (BM25 + vectors), LLM reranking, and answer synthesis to enable intelligent retrieval from personal notes.

## Key Principles

- **Local-first, privacy-preserving** — all data stays on your machine
- **Vault is the single source of truth** — no application state outside it
- **Suggestion-only** — the system recommends, never acts autonomously
- **Simple over clever** — maintainable systems over fragile ones

## Features

- **Hybrid search** — BM25 lexical + vector similarity with reciprocal rank fusion
- **LLM reranking + synthesis** — gpt-4o-mini or local Ollama for answer generation with citations
- **Metadata extraction** — summaries, entities, key phrases, action items, deadlines
- **Task management** — aggregates tasks from daily notes with bi-directional vault sync
- **Next.js dashboard** — dark "mission control" UI with chat, tasks, calendar, and insights pages
- **Dual LLM providers** — OpenAI API or local Ollama (gpt-oss, llama3.2, etc.)
- **Secure remote access** — Tailscale VPN for private mobile access

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12+, FastAPI |
| **Frontend** | Next.js 15, React 19, Tailwind CSS v4, TypeScript |
| **Documents** | SQLite (WAL mode) |
| **Vectors** | ChromaDB (local) |
| **Lexical search** | SQLite FTS5 |
| **Embeddings** | BAAI/bge-base-en-v1.5 (local) or OpenAI text-embedding-3-small |
| **LLM** | OpenAI gpt-4o-mini or local Ollama |
| **Package management** | uv (Python), npm (frontend) |

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18+ and npm (for the frontend)
- An Obsidian vault with Markdown notes

### Setup

```bash
# Clone the repo
git clone https://github.com/brendenrossin/SecondBrain.git
cd SecondBrain

# Install Python dependencies
make install

# Install frontend dependencies
make frontend-install

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your vault path and API keys

# Set up git hooks (pre-push runs lint, typecheck, and tests)
make setup-hooks
```

### Running

```bash
# Start the FastAPI backend (http://localhost:8000)
make dev

# Start the Next.js frontend (http://localhost:7860)
make frontend-dev

# Or run both together
make dev-all
```

Verify the backend is running:
```bash
curl http://localhost:8000/health
# Returns: {"status": "ok"}
```

### Index Your Vault

```bash
# With the server running:
make index

# Or standalone (no server needed):
make reindex
```

## Customize for Your Vault

After cloning, edit these files to make it yours:

1. **Environment** — Copy `.env.example` to `.env` and set `SECONDBRAIN_VAULT_PATH` to your Obsidian vault
2. **Vault folders** — Create these folders in your vault: `00_Daily/`, `10_Notes/`, `20_Projects/`, `30_Concepts/`, `Inbox/`, `Tasks/`, `90_Meta/Templates/`
3. **Frontend branding** — Edit `frontend/src/lib/config.ts` to set your display name, app name, and user initial
4. **Inbox categories** — Edit task categories and living documents at the top of `src/secondbrain/scripts/inbox_processor.py`
5. **PWA manifest** — Update `frontend/public/manifest.json` and `frontend/package.json` with your app name

## Environment Variables

```bash
SECONDBRAIN_VAULT_PATH=/path/to/obsidian/vault        # Required for indexing
SECONDBRAIN_HOST=127.0.0.1                             # API server host
SECONDBRAIN_PORT=8000                                  # API server port
SECONDBRAIN_DATA_PATH=data                             # Data storage directory
SECONDBRAIN_OPENAI_API_KEY=sk-...                      # Required for LLM features
SECONDBRAIN_EMBEDDING_PROVIDER=local                   # "local" or "openai"
SECONDBRAIN_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5     # Local embedding model
SECONDBRAIN_OPENAI_EMBEDDING_MODEL=text-embedding-3-small  # OpenAI embedding model
```

## Development Commands

```bash
# Backend
make dev           # Run FastAPI server with hot reload
make test          # Run pytest (156 tests)
make lint          # Run ruff linter
make format        # Run ruff formatter
make typecheck     # Run mypy type checker
make check         # Run all checks (lint + format-check + typecheck + test)
make eval          # Run RAG evaluation harness
make reindex       # Reindex vault standalone
make daily-sync    # Run full daily sync (inbox + tasks + reindex)
make extract       # Extract metadata from vault notes

# Frontend
make frontend-install  # Install npm dependencies
make frontend-dev      # Run Next.js dev server
make frontend-build    # Production build

# Both
make dev-all       # Run FastAPI + Next.js together
```

## Project Structure

```
src/secondbrain/
├── main.py              # FastAPI app entry point
├── config.py            # Settings (pydantic-settings)
├── models.py            # Pydantic models
├── vault/               # Vault connector + parser
├── indexing/            # Chunker + multi-provider embedder
├── stores/              # Vector (ChromaDB), lexical (FTS5), conversation
├── retrieval/           # Hybrid search + reranker
├── synthesis/           # LLM answer generation
├── eval/                # RAG evaluation harness + metrics
├── api/                 # FastAPI routes (/ask, /index, /tasks, etc.)
├── scripts/             # Daily sync, inbox processor, task aggregator
└── logging/             # Query logger (JSONL)

frontend/
├── src/app/             # Next.js app router pages
│   └── (dashboard)/     # Chat, Tasks, Calendar, Insights pages
├── src/components/      # React components (layout, chat, tasks, calendar)
├── src/lib/             # API client, utilities, types
└── public/              # Static assets
```

## Architecture

### Data Flow

1. Vault file changes detected → parse Markdown → extract frontmatter/headings/blocks
2. Create stable chunk IDs using `hash(note_path + heading_path + block)`
3. Generate embeddings → store in ChromaDB
4. Build BM25/FTS5 lexical index
5. Query: hybrid retrieve (BM25 + vectors) → LLM rerank → synthesize answer with citations

### Frontend Pages

- **Chat** — RAG-powered Q&A against your vault with conversation history
- **Tasks** — Aggregated tasks from daily notes with stat cards, filters, and category tree
- **Calendar** — Weekly agenda view with overdue tracking and due date badges
- **Insights** — Metadata summaries, entities, and note suggestions

### Daily Sync Pipeline

The daily sync (`make daily-sync`) runs three steps:
1. **Inbox processing** — routes inbox notes to daily notes and task files
2. **Task sync** — aggregates tasks from daily notes with bi-directional completion sync back to vault
3. **Reindexing** — incremental re-index of changed files + metadata extraction

This can be automated via launchd on macOS:
```bash
make install-cron    # Install daily sync at 7 AM
make uninstall-cron  # Remove the scheduled job
```

## macOS Services

The frontend can run as a persistent launchd service (auto-start on boot, auto-restart on crash):

```bash
make install-ui-service    # Install and start the UI service
make uninstall-ui-service  # Stop and remove the service
```

## Documentation

Detailed docs are in the `docs/` directory:

| Doc | Contents |
|-----|----------|
| `docs/PRD.md` | Product requirements and vision |
| `docs/ROADMAP.md` | Phased implementation plan + decisions log |
| `docs/SOLUTION_ARCHITECTURE.md` | Tech choices and rationale |
| `docs/DATA_MODEL.md` | Schema, entities, relations |
| `docs/INDEXING_PIPELINE.md` | Chunking and embedding details |
| `docs/API_SPEC.md` | REST endpoint specifications |
| `docs/SECURITY_PRIVACY.md` | Threat model and hardening |
| `docs/UI_DESIGN_SPEC.md` | Frontend design spec |
| `docs/features/*.md` | Individual feature specs and proposals |
| `docs/devlog/` | Development logs for features and error resolutions |

## Implementation Status

| Phase | Description | Status |
|-------|------------|--------|
| 0 | Repo scaffolding, CI/CD, config, Makefile | Done |
| 1 | Vault ingestion, chunker, hybrid search, retrieval API | Done |
| 2 | Incremental indexing, reranking, eval framework, embedding upgrade | Done |
| 3 | Metadata extraction, suggestions engine | Done |
| 3.5 | Next.js frontend, task aggregation, calendar, chat UI | Done |
| 4 | Secure remote access via Tailscale | Done |
| 5 | Morning briefing dashboard | Done |
| 5.5 | Inbox upgrade + Anthropic migration | Done |
| 5.7 | User configurability (branding, constants) | Done |
| 6 | LLM cost tracking + admin dashboard | Done |
| 6.5 | Quick capture | Planned |
| 7 | Weekly review generation | Planned |
| 8 | Voice chat via OpenAI Realtime API | Future |
| 9 | Knowledge graph | Future |
| 10 | Write-back workflow (PR-style changesets) | Future |

## Security

- All services bind to `127.0.0.1` by default
- Remote access only via Tailscale VPN (no public endpoints)
- API keys stored in `.env` (gitignored)
- Vault remains the source of truth — system never auto-edits notes
