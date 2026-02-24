# Implementation Prompt: Hash Mismatch Bugfix — Round 2

> **Context:** Read `docs/devlog/errors/2026-02-24-metadata-extraction-hash-mismatch-cost-explosion.md` for full background. The initial fix addressed the `daily_sync.py` code path but the PM review found the **same bug exists in the API code path** (`api/metadata.py`) plus two additional issues. This prompt covers all remaining fixes.

## Summary

The initial bugfix correctly overrides the extractor's wrong content hash in `daily_sync.py`, but the `POST /api/v1/extract` endpoint in `api/metadata.py` calls the same extractor and stores metadata **without** the hash override. This means any API-triggered extraction re-introduces the hash mismatch, causing the next hourly sync to re-extract everything. There are also two medium-severity issues with the "Today's Cost" data and usage type labeling.

## Work Items (in order)

### 1. Fix hash mismatch in `api/metadata.py` batch extraction (CRITICAL)

**File:** `src/secondbrain/api/metadata.py` lines 117-129

**Problem:** The `_extract_batch()` inner function calls `extractor.extract(note)` and stores the result directly. The returned `metadata.content_hash` is the extractor's stripped-content hash, not the raw-bytes hash from `get_file_metadata()`. This is the exact same bug that was fixed in `daily_sync.py`.

**Fix:** After `metadata = extractor.extract(note)`, override the hash before upserting:

```python
# Inside _extract_batch(), after line 123:
metadata = extractor.extract(note)
metadata.content_hash = current_hashes[path]  # Match get_file_metadata() hash
metadata_store.upsert(metadata)
```

`current_hashes` is already computed at line 103 and is in scope for the inner function (closure).

### 2. Fix hash mismatch in `api/metadata.py` single-note extraction (CRITICAL)

**File:** `src/secondbrain/api/metadata.py` lines 84-99

**Problem:** When `note_path` is provided, the endpoint extracts metadata for a single note and stores it without a hash override.

**Fix:** Compute the raw-bytes hash for the single note and override before upserting:

```python
# After line 91, before metadata_store.upsert:
import hashlib
full_path = vault_path / note_path
raw_hash = hashlib.sha1(full_path.read_bytes()).hexdigest()
metadata.content_hash = raw_hash
metadata_store.upsert(metadata)
```

Note: `vault_path` is already available at line 78. The `hashlib` import can go at the top of the file.

### 3. Fix "Today's Cost" showing wrong day's data (MEDIUM)

**File:** `src/secondbrain/api/admin.py` lines 88-91

**Problem:** `get_daily_costs(days=1)` computes `since = today - 1 day = yesterday`. The SQL returns rows from both yesterday AND today, sorted ASC. `today_data[0]` picks the **first** (oldest) entry — which is yesterday's data if any usage occurred yesterday. The "Today's Cost" card and cost alert show stale data.

**Fix:** Use the **last** entry (most recent day) instead of the first. Replace:

```python
today_data = usage_store.get_daily_costs(days=1)
today_cost = today_data[0]["cost_usd"] if today_data else 0.0
today_calls = today_data[0]["calls"] if today_data else 0
```

With:

```python
today_str = datetime.now(UTC).strftime("%Y-%m-%d")
today_data = usage_store.get_daily_costs(days=1)
today_entry = next((d for d in today_data if d["date"] == today_str), None)
today_cost = today_entry["cost_usd"] if today_entry else 0.0
today_calls = today_entry["calls"] if today_entry else 0
```

This explicitly matches on today's date string instead of assuming positional order. `datetime` and `UTC` are already imported.

### 4. Fix API extractor using wrong `usage_type` (MEDIUM)

**File:** `src/secondbrain/api/dependencies.py` lines 110-119

**Problem:** `get_llm_client()` creates `LLMClient(usage_store=get_usage_store())` with the default `usage_type="inbox"`. This client is used by `get_extractor()`, so API-triggered extractions are logged as "inbox" instead of "extraction" in the usage breakdown.

**Fix:** Create a dedicated factory for the extraction LLM client. Replace:

```python
@lru_cache
def get_llm_client() -> LLMClient:
    """Get cached LLM client instance."""
    return LLMClient(usage_store=get_usage_store())


@lru_cache
def get_extractor() -> MetadataExtractor:
    """Get cached metadata extractor instance."""
    return MetadataExtractor(get_llm_client())
```

With:

```python
@lru_cache
def get_llm_client() -> LLMClient:
    """Get cached LLM client instance."""
    return LLMClient(usage_store=get_usage_store())


@lru_cache
def get_extraction_llm_client() -> LLMClient:
    """Get cached LLM client for metadata extraction."""
    return LLMClient(usage_store=get_usage_store(), usage_type="extraction")


@lru_cache
def get_extractor() -> MetadataExtractor:
    """Get cached metadata extractor instance."""
    return MetadataExtractor(get_extraction_llm_client())
```

The existing `get_llm_client()` stays unchanged (it's used elsewhere with default "inbox" type).

## Testing Requirements

### New tests needed:

1. **`tests/test_metadata_api.py` or add to existing test file** — Test that `POST /api/v1/extract` batch extraction stores the raw-bytes hash (same pattern as `test_daily_sync.py::TestExtractMetadataHashFix::test_stored_hash_matches_vault_hash` but through the API endpoint).

2. **`tests/test_metadata_api.py`** — Test that `POST /api/v1/extract?note_path=...` single-note extraction stores the raw-bytes hash, not the extractor hash.

3. **`tests/test_admin_api.py`** — Test that "today's cost" correctly returns today's data even when yesterday also has usage. Mock `get_daily_costs` to return 2 entries (yesterday + today) and verify the response picks today's entry. Also test the case where today has zero usage but yesterday does — should return 0, not yesterday's cost.

4. **`tests/test_admin_api.py`** — Test that the cost alert triggers based on today's actual cost, not yesterday's.

### Existing tests to verify still pass:

Run `make check` (or `uv run pytest tests/ -q --tb=short && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`) to verify nothing is broken.

## What's Out of Scope

- **Do NOT refactor `_content_hash` in extractor.py** — The override pattern is fine for now. A deeper refactor (making the extractor accept hash as a parameter, or changing what it hashes) is tracked as a Low finding for future cleanup.
- **Do NOT move the cost alert threshold to pydantic-settings** — Also a Low finding, fine to leave as `os.environ.get` for now.
- **Do NOT change the "Today's Cost" stat card back to "Total LLM Calls"** — The card replacement was intentional.
- **Do NOT add tracing/observability** — That's a separate feature tracked in `docs/features/llm-observability-tracing.md`.

## Files to Modify

| File | Change |
|------|--------|
| `src/secondbrain/api/metadata.py` | Hash override in both single-note and batch extraction paths |
| `src/secondbrain/api/admin.py` | Fix today's cost to filter by today's date explicitly |
| `src/secondbrain/api/dependencies.py` | Add `get_extraction_llm_client()` factory with `usage_type="extraction"` |
| `tests/test_admin_api.py` | Add tests for today-vs-yesterday cost edge case |
| New or existing test file for metadata API | Add tests for hash consistency through API extraction |

## Commit Workflow

1. Implement all 4 work items
2. Run `/test-generation` for any new functions with business logic
3. Run `code-simplifier` before committing
4. Commit with a descriptive message referencing the hash mismatch fix
