---
spec: 001-secondbrain-recall-mcp-server-for-witt.md
spec_version: 0.3.0
reviewer: skeptic
round: 3
verdict: approve with changes
date: '2026-11-21'
---
## Skeptic review — 001 SecondBrain recall MCP server for Witt (v0.3.0, round 3)
Verdict: approve with changes

Unstated assumptions:
1. **Which major version of the MCP SDK.** The spec says "FastMCP" and "`mcp` (the official SDK, already used by Witt)". Witt pins `mcp>=2.3,<3` (`~/code/witt/pyproject.toml`) and uses `mcp.server.mcpserver.MCPServer`. In 2.x, `mcp/server/fastmcp.py` exists only to raise `ModuleNotFoundError("…FastMCP was renamed to MCPServer…")`. Not written down.
2. **How fresh the index is.** A Witt note can only be recalled after the next `POST /api/v1/index`. Today that call comes from `com.secondbrain.daily-sync` (`StartInterval` 3600, so hourly) or a manual `make index`. An ADR written by `close`, or a spec mirrored by `spec_set_status`, stays invisible for up to an hour. Not written down.
3. **In-flight specs are in the corpus.** `spec_set_status` mirrors every spec into `Witt/Projects/<slug>/specs/`. So when `spec-draft` revises a spec, recall returns that spec's own earlier mirror as "prior art". The spec handles this only inside the eval (`allowed_cohits`), not in the product. Not written down.
4. **Witt stays smaller than the retrieval windows (k_vec=30, k_lex=50).** The `project` and `kinds` filters run after those windows (Decision 6 step 7). They only avoid being crowded out while Witt has fewer chunks than the windows hold. Not written down.
5. **v1 only needs `note_folder` to be right on `Witt/` rows.** Every Witt note was indexed on 2026-11-21, after `note_folder` existed. Non-Witt rows that lack the key are correctly excluded by a Witt-only filter. The Data pre-check is broader than v1 needs. Not written down.
6. **The `.env` host and port match the API plist.** The MCP base URL comes from `Settings.host/port`, but `com.secondbrain.api.plist` hard-codes `--host 127.0.0.1 --port 8000`. Not written down.
7. **`HF_HUB_OFFLINE=1` blocks model changes.** It is set process-wide in the API plist, so any uncached model fails to load in the API, and that breaks `/ask` and indexing as well as recall. This interacts with "recalibrate when the embedder changes". The spec only says "the model is already cached".
8. **Vault inventory is out of date.** Data says "2 spec mirrors". The vault now has 3 (`Witt/Projects/witt/specs/002-hardening-backlog-from-spec-001-review.md` was added), so there are 7 non-log notes.

- [x] **BLOCKER** The MCP server is specified against an SDK API that no longer exists in the version Witt uses. Interfaces says `mcp_server.py … stdio, FastMCP` and `@mcp.tool(description=…)`. Risks says the dependency is "`mcp` (the official SDK, already used by Witt)". That is 2.x, where FastMCP was removed. Several spec claims are also version-specific: the `isError` behaviour for schema failures, "not an exception in the client", and how tools are registered. Witt's own `server.py` notes that 2.x treats any non-`ToolError` exception as a crash and hides its message. Two engineers would build against different majors. — Pin the version in Interfaces and `pyproject.toml`. Either use `mcp>=2.3,<3` with `MCPServer` and re-check every `isError` claim and the schema scenario against 2.x, or pin `mcp<2` on purpose and drop "already used by Witt". — resolved: pinned mcp>=2.3,<3 with MCPServer (verified against Witt's venv); isError claims restated for 2.x.
- [x] **BLOCKER** One MCP acceptance row contradicts the Interfaces design. The tool parameter is typed `filters: RecallFilters | None`, "so the generated inputSchema carries the kinds enum and the slug pattern". Interfaces also says arguments that fail the SDK's schema check "never reach the handler" and come back as `isError`. `RecallFilters` carries `pattern=` and `extra="forbid"`, so the SDK's argument model rejects `{"project": "Second Brain"}` before the handler runs. Yet "schema-valid but semantically invalid arguments" lists that row as "not isError, ok false". It can't pass as written, and an implementer has to pick a side. Only `query ""`, `query "***"` and `limit 0` really reach the handler. — Move the `project "Second Brain"` row into the wrong-type/`isError` scenario, and add `kinds ["log"]` and `filters {"bogus":1}` there too. Or type `filters` loosely, but that breaks the "schema carries the pattern" scenario. Pick one. — resolved: pattern, enum and extra violations moved to the isError scenario; only query/limit semantic rows remain ok:false.
- [x] **BLOCKER** The Data pre-check breaks the rule Decision 1 is built on. "Count Chroma chunks lacking the `note_folder` key" in implement step 1 means opening `data/chroma` from a second process while `com.secondbrain.api` (KeepAlive) holds it. Decision 1 and the 2026-02-06 corruption devlog both exist to forbid that. The spec doesn't say how to run it, and the obvious one-off script is `chromadb.PersistentClient(path="data/chroma")`. It's also unnecessary for v1 (assumption 5). — Narrow the check to Witt rows using the lexical store read-only, for example `sqlite3 data/lexical.db "select count(*) from chunks where note_path like 'Witt/%' and note_folder != 'Witt'"`, since both stores are written from the same `Chunk`. If a Chroma check is still wanted, require the API to be unloaded first, or go through the API. Drop the "full reindex" branch from Rollout 4 unless this check fails. — resolved: pre-check is lexical-only, read-only SQL; Chroma is never opened outside the API (Data, Decision 1).
- [x] **SHOULD** Index lag undermines "empty means nothing relevant". The pinned description says that `ok: true`, empty `hits` and no `warnings` means nothing relevant was found. For anything written in the last hour that's false, and `close` / `spec-draft` are exactly the mid-session callers who just wrote something. — State the freshness bound in Intent and Risks, and add a clause to `PINNED_DESCRIPTION` ("notes written in the last hour may not be indexed yet"). Optionally, have the Witt follow-up trigger `POST /api/v1/index` after `note_write` and `spec_set_status`. — resolved: freshness bound stated in Intent, Risks and the pinned description; Witt follow-up may trigger an index.
- [x] **SHOULD** A spec being revised recalls itself. `spec-draft` on a revision will return that spec's previous mirror as top-1 prior art. The API contract is frozen here, so the Witt follow-up can't fix it without reopening this spec. — Add an optional `exclude_paths: list[str]` (≤10, under `Witt/`) to `RecallFilters` now, applied before dedupe. Or state explicitly that callers must drop hits whose `note_path` is the spec in hand, and put that in the pinned description. — resolved: exclude_paths filter (≤10, Witt/ only) added.
- [x] **SHOULD** The project and kinds filters reintroduce the crowding problem that the folder pre-filter fixed. Once Witt has more chunks than k_vec/k_lex hold, a small project's or rare kind's chunks can fall out of both windows. Recall then returns `hits: []` with no warning, which is a false "nothing found" (the "kinds fills the limit from deep in the ranking" scenario only works while the whole corpus fits in 80 candidates). — Add a warning such as `"candidate window saturated; filtered results may be incomplete"` when either store returned a full window and step 7 dropped candidates. Or add a Risk with a concrete trigger (Witt chunk count > k_vec) tied to the "+10 notes" recalibration. — resolved: the vector window covers every Witt chunk up to 500, with a saturation notice beyond that (Decision 6).
- [x] **SHOULD** The pinned description and Decision 6 step 2 contradict each other. The description says "If `warnings` is non-empty, fix the filters and call again, because that's not a 'nothing found' answer". The warning `"vault path not configured; project slug not verified"` can't be fixed by the agent, and it comes with real hits. An agent following the description either retries in a loop or throws away valid hits. — Either return `ok: false` / 503 for a missing vault path (indexing is broken in that state anyway), or split the response into actionable `warnings` and informational `notices`, and pin the description to match. — resolved: split into actionable warnings and informational notices; description pinned to match.
- [x] **SHOULD** It's unclear which exceptions become a 503. Interfaces only names "embedder/Chroma/SQLite failure", but "recall during a reindex" requires every recall to be 200 or 503. Mid-reindex failures can be other types too (a numpy shape error in `similarities`, a `KeyError` on missing metadata). Engineers will differ on whether those become 500s, and a 500 also skips the recall log (Goal 7). — Specify a catch-all `Exception` → 503 `"recall unavailable: <Type>"`, logged with `exc_info` and a `recall_log` line. — resolved: catch-all Exception → 503 with recall_log line.
- [x] **SHOULD** Rollout 5 ("run the held-out eval until every hard gate passes") invites tuning on the held-out split. That would silently turn it into a second calibration set and void Goal 9. — Say that a held-out failure stops the rollout and goes to Brent. Any change to the floor, the dataset or the code made after seeing held-out results requires a newly written held-out split, and its sha256 changes in the report. — resolved: moot, since there's no held-out split; the gate-failure discipline is stated.
- [x] **SHOULD** It's unclear what the goldens are captured over. "Captured on main before any change" doesn't say fixture or live stores, or real or stub embedder. Live data isn't deterministic and would load bge-base in the suite, against Decision 9's reason for defaulting warmup off. — Pin the goldens to a committed fixture index built with a deterministic stub embedder. — resolved: goldens over a committed fixture index with a stub embedder.
- [x] **NIT** The drift check (Decision 11) compares `embedding_model`, but with `embedding_provider=openai` the model actually in use is `openai_embedding_model`. — Compare against `get_embedder().model_name`. — resolved: moot, since the drift check was removed; the provider check uses embedding_provider.
- [x] **NIT** "A candidate at exactly the floor is kept" compares numbers from two different computations: Chroma `1 - distance` and numpy cosine in `similarities()`. Exact equality between them doesn't mean anything. — Keep `>=`, but don't promise exact-floor behaviour for rescored candidates. Or round both to 4 decimal places before comparing. — resolved: moot, since rescoring was removed; the floor uses VectorStore's existing >= semantics.
- [x] **NIT** `VectorStore.similarities` has no reconnect-retry branch, unlike every other `VectorStore` method. — Add the same `(ChromaError, RuntimeError)` → `_reconnect()` → retry pattern, or say why it's omitted. — resolved: moot, since similarities() was removed; count_chunks gets the reconnect-retry pattern.
- [x] **NIT** Update the Data vault inventory to 7 non-log notes / 3 spec mirrors. — resolved: vault inventory updated (7 non-log notes, 3 spec mirrors).

What I checked, besides the above:
- Every round-2 skeptic resolution against v0.3.0. All hold.
- `retrieve`, the store `search` methods and their retry branches, the rowid JOIN against `content_rowid='rowid'`, and the `similarity_score=0.0` sentinel for keyword-only candidates.
- The deleted-file path in `_run_indexing` for the log exclude, and the skip-without-`mark_indexed` on bad YAML.
- Title and frontmatter handling in `parser.py`, and `note_folder` derivation in `extract_note_metadata`.
- The `models.py` import graph (no cycle), and `httpx` already being imported by `tracing.py` in main code.
- That the `slugify` output matches the slug pattern, and that `resolve_project` re-slugifies a raw `slug`.
- That `uv.lock` versions (pydantic 2.12.5, sse-starlette 3.2.0, chromadb 1.4.1) don't obviously conflict with mcp 2.3's requirements.
- The live `Witt/` tree.

Cheaper alternative considered: Witt has tens of chunks, well under k_vec. A Chroma query filtered with `where` and `n_results ≥` the Witt chunk count already returns the exact cosine for every Witt chunk. That makes `similarities()`, the rescoring step and its log fields unnecessary until Witt outgrows the window. Also, two 10-query splits calibrating a floor over 7 notes give little statistical confidence. A fixed conservative floor plus smoke queries, with calibration deferred until 30 notes (the MRR trigger you already have), is cheaper. Plain Grep over the 7 notes remains the cheapest of all.

Files reviewed:
- /Users/brentrossin/code/second-brain/docs/specs/001-secondbrain-recall-mcp-server-for-witt.md
- /Users/brentrossin/code/second-brain/docs/specs/reviews/001-secondbrain-recall-mcp-server-for-witt.skeptic.r2.md
- /Users/brentrossin/code/second-brain/src/secondbrain/retrieval/hybrid.py
- /Users/brentrossin/code/second-brain/src/secondbrain/stores/vector.py
- /Users/brentrossin/code/second-brain/src/secondbrain/stores/lexical.py
- /Users/brentrossin/code/second-brain/src/secondbrain/indexing/embedder.py
- /Users/brentrossin/code/second-brain/src/secondbrain/vault/connector.py
- /Users/brentrossin/code/second-brain/src/secondbrain/vault/parser.py
- /Users/brentrossin/code/second-brain/src/secondbrain/main.py
- /Users/brentrossin/code/second-brain/src/secondbrain/config.py
- /Users/brentrossin/code/second-brain/src/secondbrain/models.py
- /Users/brentrossin/code/second-brain/src/secondbrain/tracing.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/index.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/dependencies.py
- /Users/brentrossin/code/second-brain/src/secondbrain/scripts/daily_sync.py
- /Users/brentrossin/code/second-brain/tests/test_hybrid_rrf.py
- /Users/brentrossin/code/second-brain/pyproject.toml
- /Users/brentrossin/code/second-brain/uv.lock
- /Users/brentrossin/code/second-brain/com.secondbrain.api.plist
- /Users/brentrossin/code/second-brain/com.secondbrain.daily-sync.plist
- /Users/brentrossin/code/second-brain/etc/newsyslog.d/secondbrain.conf
- /Users/brentrossin/code/witt/src/witt/server.py
- /Users/brentrossin/code/witt/src/witt/config.py
- /Users/brentrossin/code/witt/src/witt/project.py
- /Users/brentrossin/code/witt/src/witt/vault.py
- /Users/brentrossin/code/witt/pyproject.toml
- /Users/brentrossin/code/witt/.venv/lib/python3.15/site-packages/mcp/server/fastmcp.py
- /Users/brentrossin/Obsidian-Vault/main-vault/Witt/ (tree)
