<h1 align="center">SecondBrain</h1>

<p align="center">
  <strong>AI-powered semantic memory for your Obsidian vault.</strong><br>
  <sub>Ask questions in plain English. Get answers grounded in your own notes, with citations.</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12-blue?style=flat-square" alt="Python 3.12">
  <img src="https://img.shields.io/badge/frontend-Next.js%2015-black?style=flat-square" alt="Next.js 15">
  <img src="https://img.shields.io/badge/search-hybrid%20RAG-gold?style=flat-square" alt="Hybrid RAG">
  <img src="https://img.shields.io/badge/privacy-100%25%20local-green?style=flat-square" alt="100% Local">
  <img src="https://img.shields.io/badge/tests-669%20passing-brightgreen?style=flat-square" alt="669 Tests">
</p>

---

You take notes every day -- daily journals, project plans, meeting notes, ideas. But when you need that one insight from three months ago, you're guessing at filenames and keywords.

SecondBrain turns your Obsidian vault into a **searchable knowledge base that understands meaning**, not just words. It combines hybrid semantic search, LLM synthesis, and AI-powered content ingestion into a local-first system where your vault remains the single source of truth.

Works with any directory of `.md` files -- Obsidian, plain Markdown, or any text-based note system. No proprietary formats, no lock-in.

## Highlights

**8 AI integration points** across the system, all observable and cost-tracked:

| Feature | What it does |
|---------|-------------|
| **Semantic Chat** | Ask questions in natural language, get cited answers synthesized from your notes |
| **Morning Briefing** | Daily intelligence summary -- overdue tasks, today's events, recent vault activity |
| **Knowledge Library** | Paste a URL (article, YouTube, PDF) and get a structured wiki page, reviewed by an AI safety auditor |
| **Hybrid Search** | BM25 lexical + vector embeddings + LLM reranking for precision |
| **Task Dashboard** | Checkboxes across daily notes aggregated into a live dashboard with bi-directional sync |
| **Calendar** | Weekly agenda extracted from vault events with overdue tracking |
| **Full Observability** | Every AI call traced with OpenTelemetry + Langfuse, per-call cost tracking, anomaly detection |
| **100% Local** | All data on your machine. Nothing leaves without your approval. |

## Architecture

```
                        ┌─────────────────────────────┐
                        │       Obsidian Vault         │
                        │   (Markdown + Frontmatter)   │
                        └──────────┬──────────────────┘
                                   │
                  ┌────────────────┼────────────────┐
                  ▼                                  ▼
        ┌─────────────────┐               ┌─────────────────┐
        │  Index & Embed  │               │     Ingest      │
        │ Contextual      │               │ Web, YouTube,   │
        │ chunking        │               │ PDF extraction   │
        └────────┬────────┘               └────────┬────────┘
                 ▼                                  ▼
        ┌─────────────────┐               ┌─────────────────┐
        │  Hybrid Search  │               │  Safety Auditor │
        │ BM25 + Vectors  │               │  AI review gate │
        └────────┬────────┘               └────────┬────────┘
                 ▼                                  ▼
        ┌─────────────────┐               ┌─────────────────┐
        │  Intelligence   │               │  Wiki Compiler  │
        │ Rerank, Answer, │               │  Structured     │
        │ Briefing        │               │  vault pages    │
        └─────────────────┘               └────────┬────────┘
                                                   ▼
                                            Back to Vault
```

Two pipelines:
- **Retrieval** (left): Your question goes through hybrid search, LLM reranking, and answer synthesis with citations
- **Ingestion** (right): External content is extracted, safety-audited, compiled into a wiki page, and stored back in your vault

## The Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12+, FastAPI |
| **Frontend** | Next.js 15, React 19, Tailwind CSS v4, TypeScript |
| **Vectors** | ChromaDB (local) |
| **Lexical Search** | SQLite FTS5 |
| **Embeddings** | BAAI/bge-base-en-v1.5 (local) or OpenAI text-embedding-3-small |
| **LLM** | Anthropic Claude, OpenAI, or local Ollama |
| **Observability** | OpenTelemetry + Langfuse |
| **Infrastructure** | macOS launchd services, Tailscale remote access |

## Pages

| Page | Description |
|------|------------|
| **Home** | Morning briefing -- AI-synthesized daily summary, overdue tasks, upcoming events |
| **Chat** | Semantic Q&A with hybrid retrieval, LLM reranking, cited sources, conversation history |
| **Capture** | Quick notes + URL ingestion (Knowledge Library) with safety audit pipeline |
| **Tasks** | Aggregated task tree from daily notes, bi-directional vault sync, category management |
| **Calendar** | Weekly agenda extracted from vault events with overdue tracking |
| **Admin** | Cost tracking, LLM traces, anomaly detection, sync status |
| **Insights** | Vault analytics, activity trends, category breakdown |
| **Settings** | Category management and configuration |

---

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18+ and npm (for the frontend)
- A folder of Markdown notes

### Install & Run

```bash
# Clone
git clone https://github.com/brendenrossin/SecondBrain.git
cd SecondBrain

# Backend
make install          # Install Python dependencies
cp .env.example .env  # Configure vault path and API keys
make dev              # Start API server at localhost:8000

# Frontend
make frontend-install
make frontend-dev     # Start Next.js at localhost:7860

# Index your vault
make index
```

Verify:
```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### Local-Only Setup (No API Keys)

SecondBrain can run entirely on your machine with [Ollama](https://ollama.com):

```bash
brew install ollama
ollama serve
ollama pull llama3.2:3b    # or any model that fits your hardware
```

```bash
# .env -- only vault path required
SECONDBRAIN_VAULT_PATH=/path/to/your/notes
SECONDBRAIN_OLLAMA_MODEL=llama3.2:3b
```

The chat UI has a provider toggle to switch between local and API providers.

### Customize for Your Notes

1. **Environment** -- Set `SECONDBRAIN_VAULT_PATH` in `.env` to your notes folder
2. **Folder structure** -- Create: `00_Daily/`, `10_Notes/`, `20_Projects/`, `30_Concepts/`, `Inbox/`, `Tasks/`, `90_Meta/Templates/`
3. **Branding** -- Edit `frontend/src/lib/config.ts` for display name and app name
4. **Categories** -- Edit task categories in `src/secondbrain/scripts/inbox_processor.py`

> **Obsidian users** get the best experience (in-progress checkboxes, wiki-links, etc.), but the system reads plain Markdown -- no Obsidian plugins required.

---

## Environment Variables

```bash
SECONDBRAIN_VAULT_PATH=/path/to/your/notes             # Required
SECONDBRAIN_HOST=127.0.0.1                             # API server host
SECONDBRAIN_PORT=8000                                  # API server port
SECONDBRAIN_DATA_PATH=data                             # Data storage directory

# LLM API keys (at least one, or use Ollama for fully local)
SECONDBRAIN_ANTHROPIC_API_KEY=sk-ant-...               # Anthropic Claude
SECONDBRAIN_OPENAI_API_KEY=sk-...                      # OpenAI

# Local LLM
SECONDBRAIN_OLLAMA_MODEL=llama3.2:3b
SECONDBRAIN_OLLAMA_BASE_URL=http://127.0.0.1:11434/v1

# Embeddings
SECONDBRAIN_EMBEDDING_PROVIDER=local                   # "local" or "openai"
SECONDBRAIN_EMBEDDING_MODEL=BAAI/bge-base-en-v1.5
```

## Development

```bash
make check     # All checks (lint + format + typecheck + 669 tests)
make test      # Run pytest
make lint      # Run ruff
make format    # Run ruff formatter
make typecheck # Run mypy
make eval      # RAG evaluation harness
```

### Project Structure

```
src/secondbrain/
├── main.py              # FastAPI entry point
├── config.py            # Settings (pydantic-settings)
├── vault/               # Vault connector + parser
├── indexing/            # Chunker + embeddings + contextual retrieval
├── stores/              # Vector (ChromaDB), lexical (FTS5), usage, conversation
├── retrieval/           # Hybrid search + LLM reranker
├── synthesis/           # Answer generation with citations
├── ingestion/           # Content ingestion, safety auditor, wiki compiler
├── api/                 # FastAPI routes
├── scripts/             # Daily sync, inbox processor, task aggregator
└── tracing/             # OpenTelemetry + Langfuse integration

frontend/
├── src/app/(dashboard)/ # Next.js pages (Chat, Tasks, Calendar, etc.)
├── src/components/      # React components
├── src/lib/             # API client, utilities, types
└── public/              # Static assets, PWA manifest
```

### Daily Sync Pipeline

The daily sync (`make daily-sync`) runs automatically via launchd:
1. **Inbox processing** -- routes inbox notes to daily notes and task files
2. **Task sync** -- aggregates tasks with bi-directional completion sync
3. **Reindexing** -- incremental re-index of changed files + metadata extraction
4. **Usage pruning** -- removes usage records older than 90 days

```bash
make install-cron    # Install hourly sync via launchd
make uninstall-cron  # Remove the scheduled job
```

### macOS Services

```bash
make install-api-service   # Persistent API server (auto-restart)
make install-ui-service    # Persistent frontend (auto-restart)
```

## Key Principles

- **Vault is truth** -- No application state outside your Markdown files and derived indexes
- **Local-first** -- All data stays on your machine by default
- **Suggestion-only** -- The system recommends, never acts autonomously on your notes
- **Safety-gated** -- External content passes an AI safety auditor before entering the vault
- **Observable** -- Every LLM call is traced, costed, and anomaly-checked

## Documentation

Detailed docs in `docs/`:

| Doc | Contents |
|-----|----------|
| `ROADMAP.md` | Active work organized by epic, ticket statuses |
| `DELIVERED.md` | Completed work archive |
| `SOLUTION_ARCHITECTURE.md` | Tech choices and rationale |
| `DATA_MODEL.md` | Schema, entities, relations |
| `API_SPEC.md` | REST endpoint specifications |
| `SECURITY_PRIVACY.md` | Threat model and hardening |
| `features/*.md` | Individual feature specs |

## Security

- All services bind to `127.0.0.1` by default
- Remote access only via Tailscale VPN (no public endpoints)
- API keys stored in `.env` (gitignored)
- Vault remains the source of truth -- system never auto-edits notes
- External content gated by AI safety auditor

## License

This project is currently private. Contact [@brendenrossin](https://github.com/brendenrossin) for access.
