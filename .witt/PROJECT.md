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
- `test_cmd` = the full suite: 1162 tests in about 50–70s (2026-11-22, after spec 004). It's
  still fine for the synchronous Implemented gate.
  `make check` = ruff + mypy + pytest.
- Recall dataset checks (spec 004, ADR-006): pytest checks `recall_queries.yaml` structurally, and
  live-vault drift only raises a `RecallDatasetDriftWarning`. The recall eval is the hard gate. Don't
  quote a null query's `must_not_appear` term in a Witt note, or the eval fails on "null
  contamination". Don't add `filterwarnings = ["error"]`.
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
| `com.secondbrain.api` | `caffeinate -ims uv run uvicorn secondbrain.main:app` on **127.0.0.1:8000** | KeepAlive. `caffeinate` stops the Mac Studio sleeping so Tailscale stays up. Health: `GET /health`. Routes under `/api/v1`. Env `HF_HUB_OFFLINE=1` (spec 001): the cached embedder loads with no hub call. Unset it temporarily when changing embedders. |
| `com.secondbrain.ui` | `npm run start` in `frontend/` on **127.0.0.1:7860** | Next.js prod build. After frontend edits: `npm run build`, then restart. |
| `com.secondbrain.daily-sync` | `uv run python -m secondbrain.scripts.daily_sync all` every 3600s | inbox → tasks → projects → index → extract → weekly → feed. Feed runs last and swallows its own errors. |
| `com.secondbrain.langfuse` | `etc/langfuse/start.sh`: starts Docker Desktop if needed → `compose up -d --wait` → waits for :3000 health → kickstarts the API | KeepAlive `SuccessfulExit=false` (retries failures every 60s, stays down after success). Optional trace viewer. Logs to `data/langfuse.log`. Spec 002. |

**Data** (`data/`, gitignored):
- ChromaDB `PersistentClient` at `data/chroma/`, collection `chunks`.
- SQLite (WAL): `lexical.db` (FTS5), `index_tracker.db`, `index_cache.db`, `conversations.db`,
  `metadata.db`, `usage.db`, `feed.db`.
- OTel spans are written as JSONL to `data/traces/YYYY-MM-DD.jsonl`.
- Logs go to `data/logs/` and are rotated by `etc/newsyslog.d/secondbrain.conf`.
- `data/recall_log.jsonl`: one line per served recall (200 or 503), rotated by the same conf.
- `data/eval/recall-*.json`: recall eval reports.

**Recall (spec 001):** `secondbrain-mcp` (`src/secondbrain/mcp_server.py`, console script in
`.venv/bin/`) is a stdio MCP server with one typed `recall` tool. It's a thin httpx client over
`POST /api/v1/recall` (`api/recall.py`) and never opens the stores. The base URL comes from `.env`
host/port, which must match the plist. Recall is retrieval-only, over `Witt/` notes:
- hybrid search with no rerank and no LLM
- a fixed sanity floor, `SECONDBRAIN_RECALL_MIN_SIMILARITY` (default 0.40, min 0.3)
- requires `embedding_provider=local`, else 503
- zero spans
- its own per-request read-only `lexical.db` connection

`SECONDBRAIN_EMBEDDER_WARMUP=true` loads the model at API startup. Kind and project come from the
Witt path layout (`vault/witt.py`). Quality is checked by `uv run python -m secondbrain.eval.recall_eval`
against the live API.

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
- Phases 0–4 are delivered: ENGAGE-1 (PR #12), FEED-1 (PR #13), the Langfuse skip fix (PR #14), and
  the Gemma 4 fix with the Witt adoption (PR #15).
- **Specs 001–004 are Implemented.** Spec 001 (recall MCP) is PRs #16–#18. Spec 002 is Langfuse at
  login. Spec 003 (repo UI plist = installed Next.js) and spec 004 (recall hardening) are PR #21 plus
  the rollout PR #22, both 2026-11-22.
- Recall eval baseline (2026-11-23): PASS, recall@1 0.91, MRR 0.94, warm p95 about 143 ms, over 44 Witt
  notes / 1108 chunks with the MRR gate on. It was 1.00/1.00 over 18 notes. The drop is corpus growth:
  the ADR-002 query now ranks 3rd.
- Spec 005 (dev-tooling scout) was Abandoned in favour of Radar (`~/code/radar`, ADR-011).
- **Next:** see the deferred lists in spec 004's Risks section and in
  `docs/optimizations/001-recall-backlog.md`, plus the ENGAGE and FEED epics in `docs/ROADMAP.md`.

## Domain notes
**Known issues (2026-11-21):**
- **Langfuse is optional.** Fixed by spec 002 (start script plus retries). The API still probes
  Langfuse only at its own startup and falls back to JSONL only (PR #14), so the script restarts
  the API once Langfuse is healthy. Nothing may depend on Langfuse.
- **Repo plists match the installed ones** (spec 003). `make install-ui-service` doesn't build
  `frontend/.next` first, so run `npm run build` before installing on a fresh clone.
- **Witt indexing policy (spec 001):** `Witt/Logs/*` is excluded from the index. Every other Witt
  note is indexed and recallable after the next hourly index run.
- **Traceloop logs `Error initializing MCP instrumentor`** at API startup since `mcp` 2.x became a
  dependency (spec 001). It's harmless: Traceloop's MCP instrumentor expects the 1.x API.
- **FTS5:** never use content-sync triggers with `INSERT OR REPLACE`. Use an explicit `'rebuild'` after writes.
- **Tailwind v4:** no custom CSS outside `@layer` in `globals.css`.
- **`answer_stream()`** still blocks the event loop during token generation (acceptable for one user).
- **trace-eval** (`~/code/trace-eval/tests/integration/test_secondbrain_validation.py`, 9 tests) reads
  `data/traces/*.jsonl` directly, so the trace JSONL format is an external contract. The tests skip,
  rather than fail, if the directory is missing.
