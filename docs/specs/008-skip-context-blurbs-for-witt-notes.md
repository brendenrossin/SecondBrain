---
id: 008
title: Skip context blurbs for Witt notes
project: second-brain
tier: quick
status: Implemented
version: 0.1.0
created: '2026-11-22'
updated: '2026-11-22'
tags: []
history:
- status: Draft
  date: '2026-11-22'
  note: created
- status: Approved
  date: '2026-11-22'
  note: gate passed
- status: Implemented
  date: '2026-11-22'
  note: gate passed
---
# 008 — Skip context blurbs for Witt notes

## Intent
Spec 007 makes contextual-retrieval blurbs about 89% cheaper per note. But `Witt/` notes are where
the remaining spend concentrates:
- Specs are long (12k–33k tokens).
- They are rewritten through every review round and re-mirrored to the vault on every status
  change, so their chunks keep changing and miss the blurb cache.

Blurbs also add little for these notes:
- Every Witt chunk already carries its note title and heading path.
- Recall filters by project and kind.
- The recall baseline in `.witt/PROJECT.md` (recall@1 0.91, MRR 0.94 over 44 Witt notes) was
  measured after the Anthropic usage limit hit on 2026-11-22. From then on, every blurb call
  failed, so many of those Witt chunks had empty blurbs.

Brent decided (2026-11-22): skip blurb generation for any note under `Witt/`. That means zero
LLM spend on Witt churn.

The check is the recall eval. It runs on the local embedder with no LLM calls, so it costs
nothing. It must still PASS its gates after a reindex.
- Existing Witt blurbs stay until that note is next modified. Then it is re-chunked and indexed
  without one.
- Non-Witt notes keep blurbs, with 007's caching.

## Acceptance Criteria
```gherkin
Feature: No context blurbs for Witt notes

  Scenario: A Witt note makes no API call and gets empty blurbs
    Given a ContextGenerator with a usage store
    When generate_blurbs runs for 3 chunks whose note_path is "Witt/Projects/second-brain/specs/006-x.md"
    Then it returns ["", "", ""]
    And messages.create is never called and nothing is logged to the usage store

  Scenario: A non-Witt note still gets blurbs
    Given a ContextGenerator
    When generate_blurbs runs for 2 chunks whose note_path is "10_Notes/Test.md"
    Then messages.create is called twice and both blurbs are returned

  Scenario Outline: Only paths whose first segment is the Witt folder are skipped
    Then is_witt_path("<path>") is <result>

    Examples:
      | path                                   | result |
      | Witt/Learnings/n.md                    | True   |
      | Witt/Projects/witt/decisions/ADR-1.md  | True   |
      | 10_Notes/Witt/notes.md                 | False  |
      | Wittgenstein/Tractatus.md              | False  |
      | 10_Notes/Test.md                       | False  |
      |                                        | False  |

  Scenario: The recall eval still passes after reindexing
    Given the change is deployed and the vault is reindexed
    When `uv run python -m secondbrain.eval.recall_eval` runs
    Then it reports PASS on its gates, with the recall@1 and MRR recorded in the Witt log next to the 0.91 / 0.94 baseline
```

## Files
| File | Action | Note |
|---|---|---|
| `src/secondbrain/vault/witt.py` | Update | `is_witt_path(note_path) -> bool` (first path segment equals `WITT_FOLDER`) |
| `src/secondbrain/indexing/context.py` | Update | `generate_blurbs` returns `""` for Witt chunks without calling the API; this covers both indexing call sites (`api/index.py`, `api/dependencies.py`) |
| `tests/test_context_generator.py` | Update | Witt-skip and non-Witt scenarios |
| `tests/test_witt_layout.py` | Update | `is_witt_path` outline |
