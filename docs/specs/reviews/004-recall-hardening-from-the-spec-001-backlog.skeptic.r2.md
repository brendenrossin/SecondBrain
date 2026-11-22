---
spec: 004-recall-hardening-from-the-spec-001-backlog.md
spec_version: 0.2.0
reviewer: skeptic
round: 2
verdict: approve with changes
date: '2026-11-22'
---
## Skeptic review — 004 (v0.2.0, round 2)
Verdict: approve with changes

Unstated assumptions:
1. The LEXONLY note set is its own vault and index, separate from `FIXTURE_VAULT`. Not written down. The Files row only says "LEXONLY note set builder" in `tests/fixtures/recall/index.py`. If those notes go into `FIXTURE_VAULT`, every test that asserts `witt_chunk_count == 7` breaks (`test_witt_only_recall_returns_best_decision_first`, `test_recall_log_line_has_the_full_schema`, the new Goal 4 outline), and so does the TEST_QUERY golden.
2. Renaming `_ReadOnlyLexicalStore` to `_VectorLedReader` breaks existing tests that patch the class by name. Not written down. `_inject` (`tests/test_recall_api.py:646`) patches `recall_module._ReadOnlyLexicalStore.conn`, and `test_vector_window_covers_every_witt_chunk_up_to_500` (`:297`) patches its `count_chunks`. The Files row only says the `spies` and `HybridRetriever` patches "stay valid".
3. A cancelled request writes no log line, because `CancelledError` is a `BaseException` and the catch-all is `except Exception`. Not written down. It sits uneasily with the Intent's "every failure gives a logged 503".
4. `os.open(..., 0o600)` gives 0600 "whatever the process umask". That's only true when the umask doesn't clear owner bits; a umask of 0o277 gives 0400. Partly written down (Decision 3). The AC pins umask 022, which is fine.
5. A missing `expected` file still fails the eval, but with exit 1 through the existing `stale_labels` gate, not exit 2. `check_live_dataset`'s "expected file missing" also ignores `_is_excluded`, which `stale_labels` checks. Not written down.
6. The Rollout commands run from the repo root in zsh. Not written down (see the SHOULD below).
7. Pytest doesn't escalate warnings to errors. Written down (Decision 4, plus a `pyproject.toml` comment). I checked: `[tool.pytest.ini_options]` has no `filterwarnings`.
8. The live API writes to the repo's `data/`. Written down (Rollout step 2), but there's no instruction if the `lsof` check shows a different path. Your project memory says the launchd service starts in `/Users/brentrossin/SecondBrain/`.

- [x] **SHOULD** Goal 12 says "The eval still fails on either (exit 2)", but one of the two new drift kinds never gives exit 2. — `validate_dataset` = structural + corpus problems, so those give exit 2. "expected file missing" is only in `check_live_dataset`, and in the eval it becomes a `stale_labels` gate failure, exit 1. That's a small contradiction between Goal 12 and Decision 4, and an engineer could "fix" it by adding the missing-file check to `validate_dataset`. — State that a missing expected file is caught by `stale_labels` (exit 1) and stays there. Either make the drift check also skip `_is_excluded` paths the way `stale_labels` does, or say why it differs. — resolved: stale label stays stale_labels exit 1; shared _is_indexed_label honours _is_excluded
- [x] **SHOULD** Say that the LEXONLY fixture is a separate vault and index, and which index `capture_goldens.py` uses to capture LEXONLY_QUERY golden hits. — Two engineers would build it differently, and one of the two ways silently changes the TEST_QUERY golden and the 7-chunk assertions. — Add one line to Decision 1 or the Files row: "a separate vault built by `build_lexonly_index()`; the golden for LEXONLY_QUERY is captured on that index." — resolved: LEXONLY is a separate vault/index via build_lexonly_index(); FIXTURE_VAULT unchanged
- [x] **SHOULD** Account for the class rename in tests. — Patches by name start raising `AttributeError`, and an implementer may "fix" it by keeping a `_ReadOnlyLexicalStore` alias. That alias would be a second name for a store that lies about `get_chunk`, which is exactly the trap the Risks section warns about. — List `_inject` and `test_vector_window_covers_every_witt_chunk_up_to_500` in the `tests/test_recall_api.py` Files row as updated to `_VectorLedReader`, and say there is no alias. — resolved: renames listed in Files; no _ReadOnlyLexicalStore alias (Decision 1)
- [x] **SHOULD** Rollout step 3 fails as written in zsh. — `chmod 600 data/recall_log.jsonl data/recall_log.jsonl.*` hits zsh's NOMATCH when no rotated archive exists yet. The rotation size is 5120 KB, so there may be none. zsh then aborts the whole command, and the live file stays 0644. The step uses a relative path too. — Use `cd /Users/brentrossin/code/second-brain && chmod 600 data/recall_log.jsonl data/recall_log.jsonl.*(N)` or `find data -name 'recall_log.jsonl*' -exec chmod 600 {} +`. Then add a check: `stat -f %Lp data/recall_log.jsonl` prints `600`. Also say what to do if step 2's `lsof` shows a path other than the conf's. — resolved: find … -exec chmod 600 from the repo root, then a stat check; stop-and-fix if the path differs (installed plist WorkingDirectory verified as /Users/brentrossin/code/second-brain — the memory note saying ~/SecondBrain is stale)
- [x] **NIT** Decision 2's step list puts "set `holder.lexical_only_skipped` from the reader before it closes" after a `return`, where it can never run. — Say it goes in the `finally`, or just before each return. — resolved: copy happens in the finally
- [x] **NIT** Goal 13's precondition, "an unfiltered `HybridRetriever.retrieve(TEST_QUERY)` ranks 10_Notes first", doesn't say which constructor arguments it uses (default `k_vec`/floor or recall's). — Say "default-constructed, as in `goldens.json["retrieve"]`". That entry already holds this precondition, so the test could assert against it. — resolved: default-constructed, as recorded in goldens.json["retrieve"]
- [x] **NIT** `RecallDatasetDriftWarning` messages are the bare reason strings, for example "null contamination". They don't name the query or term, so the warning tells Brent something drifted but not what. — Add the offending term or path to the warning text; `structural_problems`/`corpus_problems` can keep their exact strings. — resolved: warnings name the offending term/path; returned strings unchanged
- [x] **NIT** `VectorStore.clear()` also sets `self._collection = None` outside the lock. That's the same class of race Goal 8 closes. — Lock it as well, or name it as out of scope. — resolved: clear() also runs under _init_lock, with a scenario

What I checked and found sound:
- **Decision 1 leaves the 200 hits unchanged.** `HybridRetriever.retrieve` calls `get_chunk` only for ids missing from `vector_data`, skips any `None` result before the `top_k` slice, and computes RRF per id. Vector results below the floor count as lexical-only, which matches today's `_rank` drop.
- **The Goal 4 numbers hold.** The `embedder`, `chroma` and `fts` injections all fail after `COUNT(*)`, so 7 / 30 holds. The `count` row correctly logs 0.
- **Warmup cancellation is clean.** `_warm_up` catches `Exception` only, so the task does end `cancelled()` with no WARNING.
- **The cap is per entry, and the list is already bounded.** `exclude_paths` already has `max_length=10`.
- **The snippet rows are right.** With `make_snippet`, the 600 row gives `text[:600]` and the 590–594 row gives `text[:594]`.
- **Archives keep their mode.** newsyslog flags are `N` with no compression, so rotated archives are renames, as the spec says.
- **The r1 items are resolved.** Every round-1 item is resolved in v0.2.0, and none has come back.

Cheaper alternative considered: For Goal 12, delete `test_recall_queries_yaml_validates` and keep only the new structural test, leaving the eval as the sole live gate. That drops `check_live_dataset`, the warning class and three tests. It loses only a warning that is easy to ignore, which Risks already concedes. Keeping it is defensible, but it's the first thing to cut. The rest of the batch is already minimal per item.
