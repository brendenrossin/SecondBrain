---
spec: 001-secondbrain-recall-mcp-server-for-witt.md
spec_version: 0.2.0
reviewer: architect
round: 2
verdict: approve with changes
date: '2026-11-21'
---
## Architect review — 001
Verdict: approve with changes

I traced one recall through the code: MCP, then `POST /api/v1/recall`, then `get_retriever()` (an `lru_cache` singleton), then `HybridRetriever.retrieve`, then `VectorStore.search` / `LexicalStore.search`, then RRF. The shape holds. The thin HTTP client is the right decision, given that `PersistentClient` must have one owner and the embedder is warm in the API process. Every existing `.retrieve(` caller (`ask.py:90,176`, `capture.py:49`, `eval_harness.py:93`, `ui.py:333`) passes positional args, so keyword-only folder arguments are additive. The span suppression claim is checked against the installed instrumentor. `opentelemetry/instrumentation/chromadb/wrapper.py:36` returns early on `_SUPPRESS_INSTRUMENTATION_KEY`, and no FastAPI, ASGI or sqlite instrumentor is installed. The log removal claim also holds: an excluded file drops out of `get_file_metadata`, so `classify_changes` reports it as deleted, and `_run_indexing` (`api/index.py:85-89`) then deletes it from both stores and the tracker.

- [x] **SHOULD** Putting `RecallKind` in `vault/witt.py` creates a circular import. `models.py` would import `secondbrain.vault.witt`. That runs `secondbrain/vault/__init__.py`, which imports `connector.py`, which runs `from secondbrain.models import Note` while `models` is only partly loaded, so the import fails. — Define `RecallKind` in `models.py`, which imports nothing from `secondbrain`, and have `vault/witt.py` import it from there. Then `models.py` never imports the `vault` package. — resolved: RecallKind moved to models.py; witt.py imports it from there (Decision 5).
- [x] **SHOULD** The calibration procedure can't run over HTTP as specified. "Run with the floor disabled" requires restarting the live API with `SECONDBRAIN_RECALL_MIN_SIMILARITY=0` and then restarting it again. Even then, null queries show no similarity, because their candidates are dropped. There is also a second floor nobody mentions: the shared retriever's vector `min_similarity=0.3` (`hybrid.py:38`, applied in `vector.py:207`). That makes 0.3 the effective minimum, and a candidate outside the k_vec=30 window has similarity 0, which is different from being below the floor. — Add `max_dropped_similarity` (the best similarity among candidates dropped by the floor) to the recall log line, and optionally to the response. The eval can then calibrate with the floor in place and no restart. State in the spec that a calibrated floor below 0.3 is not achievable without changing the retriever's own threshold. — resolved: calibration runs with the floor in place using explain=true candidates (no restart); floor ≥ 0.3 stated.
- [x] **SHOULD** Warmup races the first recall. `SentenceTransformerProvider._st_model` (`indexing/embedder.py:100-105`) lazy-loads with no lock. A recall that arrives while the Decision 9 warmup thread is still loading starts a second bge-base load, which costs about 400 MB more and double the load time. That is exactly the window warmup exists to cover, and it gets worse with the 8-concurrent scenario on a cold model. — Add a `threading.Lock` around the lazy load. Add `indexing/embedder.py` to Files with a test. Also say how the fire-and-forget task is held. `asyncio.to_thread` returns a coroutine, so it needs `asyncio.create_task`, a stored reference, and a wrapper that logs exceptions so they don't surface as "Task exception was never retrieved". — resolved: locked lazy load; warmup task held on app.state with an exception-logging wrapper; embedder.py added to Files.
- [x] **SHOULD** The "no network calls at all" claim (Intent, Decision 10) is untrue on the first model load. Loading `SentenceTransformer(model_name)` contacts the Hugging Face hub unless `HF_HUB_OFFLINE=1` is set, and the `requests`/`urllib3` instrumentors are active. With warmup off, which is the default, that first load happens on a recall. — Either qualify the claim as "per query, once the model is loaded", or set `HF_HUB_OFFLINE=1` in the launchd plist or `.env` as a Rollout step. — resolved: HF_HUB_OFFLINE=1 in Rollout; claim qualified in Intent and Decision 10.
- [x] **SHOULD** `scope="witt"` has a silent-miss path the spec doesn't cover. Lexical rows written before the `note_folder` migration carry `note_folder=''` (the `lexical.py:130` default), so `IN ('Witt')` drops them, just as Chroma drops chunks missing the key. — Extend Implement step 1's count to lexical rows: `note_folder = '' AND note_path LIKE '%/%'`. Use the same full-reindex trigger. — resolved: Data pre-check also counts lexical rows with note_folder '' and a '/' in note_path.
- [x] **SHOULD** The known-slug lookup in Decision 6 reads `<vault>/Witt/Projects/`, but `settings.vault_path` is `Path | None`, and `main.py:42` already allows startup with a missing vault. — Specify the behaviour for that case: no warning, or a warning saying "vault path not configured", and never a 503 for a read that is only advisory. Add a scenario. — resolved: missing vault path skips the slug check with an advisory warning, never 503; scenario added.
- [x] **NIT** The lexical JOIN on `chunk_id` makes FTS5 fetch the external-content row a second time. `JOIN chunks c ON c.rowid = chunks_fts.rowid` matches `content_rowid='rowid'` and is cheaper. — resolved: JOIN switched to c.rowid = chunks_fts.rowid.
- [x] **NIT** `kinds` and `project` are filtered after retrieval, which is fine in `scope="witt"` (a tiny corpus). With `scope="vault"` and a `kinds` filter, the k_vec=30 window across the whole vault may contain no matching chunks. Note that limitation where you discuss fill rate, so an empty result there isn't read as "nothing relevant". — resolved: scope='vault' cut to v2 (Brent), so post-filters only run over the small Witt set.
- [x] **NIT** `dropped_below_floor` lumps two cases together: BM25-only candidates (similarity 0 because they fell outside the vector window) and genuine below-floor vector hits. Log the two counts separately so replay is unambiguous. — resolved: dropped_below_floor split into vector and keyword-only counts.
- [x] **NIT** The MCP process builds the full `Settings`, so the API keys from `.env` are loaded into a process that only needs `host` and `port`. Either accept that explicitly or read only those two fields. — resolved: accepted explicitly in the Interfaces docstring (same user, same machine).

Decisions worth an ADR:
- Thin HTTP MCP client over the API as the single store owner, rather than direct ChromaDB access (Decision 1).
- Excluding `Witt/Logs/*` at `VaultConnector` level, which also removes logs from `/ask` and metadata extraction (Decision 3).
- Witt kind and project derived from vault path layout as a cross-repo contract (Decision 5, Data "Witt note contract").

Files referenced:
- /Users/brentrossin/code/second-brain/docs/specs/001-secondbrain-recall-mcp-server-for-witt.md
- /Users/brentrossin/code/second-brain/src/secondbrain/retrieval/hybrid.py
- /Users/brentrossin/code/second-brain/src/secondbrain/stores/vector.py
- /Users/brentrossin/code/second-brain/src/secondbrain/stores/lexical.py
- /Users/brentrossin/code/second-brain/src/secondbrain/vault/connector.py
- /Users/brentrossin/code/second-brain/src/secondbrain/vault/__init__.py
- /Users/brentrossin/code/second-brain/src/secondbrain/models.py
- /Users/brentrossin/code/second-brain/src/secondbrain/indexing/embedder.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/index.py
- /Users/brentrossin/code/second-brain/src/secondbrain/api/dependencies.py
- /Users/brentrossin/code/second-brain/src/secondbrain/main.py
- /Users/brentrossin/code/second-brain/src/secondbrain/tracing.py
- /Users/brentrossin/code/second-brain/.venv/lib/python3.12/site-packages/opentelemetry/instrumentation/chromadb/wrapper.py
