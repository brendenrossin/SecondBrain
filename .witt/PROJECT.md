---
slug: second-brain
description: 'Local-first semantic memory over the Obsidian vault: hybrid search (BM25
  + vectors), LLM rerank + synthesis, Next.js Mission Control UI, daily sync.'
specs_dir: docs/specs
test_cmd: uv run python -m pytest -q
created: '2026-11-21'
---
# Project context

<!-- The living brief for this repo. witt_brief shows this every session — keep it short and current.
     Update "Current state" in the `close` skill. -->

## What it is
SecondBrain is Brent's personal semantic memory over the Obsidian vault at
`~/Obsidian-Vault/main-vault`. It indexes the vault's notes and answers questions with citations
using hybrid retrieval (BM25 + vectors), an LLM rerank and grounded synthesis. It also runs task
aggregation, a daily briefing and digest, and an RSS feed (FEED-1). It is local-first and
suggestion-only, and the vault is the single source of truth.

## Stack & conventions
- Python 3 + FastAPI (`src/secondbrain/`), managed with `uv`. **Always `uv run python -m pytest`**:
  plain `uv run pytest` resolves to Anaconda's pytest.
- Frontend: Next.js 15 in `frontend/`, served as a production build (`npm run start`). Gradio
  (`secondbrain.ui`) is deprecated.
- `test_cmd` = the full suite: 918 tests in about 12s (timed 2026-11-21), so it's safe for the
  synchronous Implemented gate. `make check` = ruff + mypy + pytest.
- Settings come from `config.py` (pydantic-settings, `SECONDBRAIN_` prefix, `.env` at the repo root).
- LLMs: Anthropic `claude-haiku-4-5` by default for rerank and answers, with an OpenAI option and a
  local Ollama option (`gemma4:26b-a4b-it-qat` for both rerank and synthesis, `reasoning_effort: "none"`).
- Embeddings: local `BAAI/bge-base-en-v1.5` (`SECONDBRAIN_EMBEDDING_PROVIDER=local`).
- Repo process docs live in `docs/ROADMAP.md`, `docs/DELIVERED.md` and `docs/features/*.md` (pre-Witt).
  New non-trivial work starts as a Witt spec in `docs/specs/`.

## Architecture in brief
**launchd services** (`~/Library/LaunchAgents/`):

| Label | What it runs | Notes |
|---|---|---|
| `com.secondbrain.api` | `caffeinate -ims uv run uvicorn secondbrain.main:app` on **127.0.0.1:8000** | KeepAlive. `caffeinate` stops the Mac Studio sleeping so Tailscale stays up. Health: `GET /health`. Routes under `/api/v1`. |
| `com.secondbrain.ui` | `npm run start` in `frontend/` on **127.0.0.1:7860** | Next.js prod build. After frontend edits: `npm run build`, then restart. |
| `com.secondbrain.daily-sync` | `uv run python -m secondbrain.scripts.daily_sync all` every 3600s | inbox → tasks → projects → index → extract → weekly → feed. Feed runs last and swallows its own errors. |
| `com.secondbrain.langfuse` | `etc/langfuse/start.sh`: starts Docker Desktop if needed → `compose up -d --wait` → waits for :3000 health → kickstarts the API | KeepAlive `SuccessfulExit=false` (retries failures every 60s, stays down after success). Optional trace viewer. Logs to `data/langfuse.log`. Spec 002. |

**Data** (`data/`, gitignored):
- ChromaDB `PersistentClient` at `data/chroma/`, collection `chunks`.
- SQLite (WAL): `lexical.db` (FTS5), `index_tracker.db`, `index_cache.db`, `conversations.db`,
  `metadata.db`, `usage.db`, `feed.db`.
- OTel spans are written as JSONL to `data/traces/YYYY-MM-DD.jsonl`.
- Logs go to `data/logs/` and are rotated by `etc/newsyslog.d/secondbrain.conf`.

**Ingestion:**
1. `VaultConnector` globs `**/*.md` under `SECONDBRAIN_VAULT_PATH` (`~/Obsidian-Vault/main-vault`) and
   applies `DEFAULT_EXCLUDES` (`.obsidian`, `.trash`, `Inbox/*`, templates, the aggregated task files…).
2. `parse_markdown` (python-frontmatter) strips the YAML frontmatter. Only `title` (used as the note
   title) and `date` (used as `note_date`) are used downstream.
3. `note_folder` is the first path segment.
4. Notes are chunked by heading, given optional Haiku context blurbs, embedded, and written to
   Chroma + FTS5.

**Indexing has one owner: the API process.** ChromaDB `PersistentClient` is single-process. The
daily sync and `make index` call `POST /api/v1/index` → `_run_indexing` (`api/index.py`), which
reindexes incrementally (mtime + sha1 via `index_tracker`) and takes **no** lock.
`check_and_reindex` (`api/dependencies.py`, which uses the `.reindex_needed` trigger and
`.reindex_lock`) is only called from the deprecated Gradio `ui.py`. Never open the stores from a
second process.

## Current state
- Phases 0–4 are delivered: ENGAGE-1 (PR #12) and FEED-1 (PR #13), with the Langfuse skip fix in PR #14.
- Branch `fix/local-gemma4-reasoning` has the Gemma 4 empty-answer fix plus the path commit for
  the move from `~/SecondBrain` to `~/code/second-brain`.
- Witt adopted 2026-11-21. In flight: spec 001, the SecondBrain MCP `recall` tool for Witt.

## Domain notes
**Known issues (2026-11-21):**
- **Langfuse is optional.** Fixed by spec 002 (start script plus retries). The API still probes
  Langfuse only at its own startup and falls back to JSONL only (PR #14), so the script restarts
  the API once Langfuse is healthy. Nothing may depend on Langfuse.
- **Repo `com.secondbrain.ui.plist` is stale.** It still launches Gradio (`python -m secondbrain.ui`).
  The installed copy runs `npm run start` in `frontend/`. Reconcile before anyone re-installs from the repo.
- **Witt notes are indexed today.** `Witt/` isn't excluded, so log, hub and ADR chunks are in the index.
  Spec 001 decides the policy.
- **FTS5:** never use content-sync triggers with `INSERT OR REPLACE`. Use an explicit `'rebuild'` after writes.
- **Tailwind v4:** no custom CSS outside `@layer` in `globals.css`.
- **`answer_stream()`** still blocks the event loop during token generation (acceptable for one user).
- **trace-eval** (`~/code/trace-eval/tests/integration/test_secondbrain_validation.py`, 9 tests) reads
  `data/traces/*.jsonl` directly, so the trace JSONL format is an external contract. The tests skip,
  rather than fail, if the directory is missing.
