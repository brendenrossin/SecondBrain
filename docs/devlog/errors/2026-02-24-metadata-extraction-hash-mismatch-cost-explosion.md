# Error: Metadata Extraction Hash Mismatch Causing Cost Explosion

**Date:** 2026-02-24
**Severity:** High
**Component:** Metadata extraction pipeline (`daily_sync.py`, `extractor.py`, `VaultConnector`)

## Symptoms

- Admin dashboard showed ~$0.03/day LLM cost, but actual Anthropic billing was ~$8-10/day
- Every hourly extraction run reported "Extracted 35" (all vault notes) instead of "All notes up to date"
- ~840 unnecessary Sonnet API calls per day (35 notes × 24 hourly runs), consuming 800K+ tokens/day
- At Sonnet pricing ($3/M input, $15/M output): ~2.1M input + ~250K output tokens/day = ~$10/day wasted
- `usage.db` had no records for extraction calls — only inbox/chat calls were tracked

## Root Cause

**Two independent bugs compounding each other:**

1. **Hash mismatch between connector and extractor:**
   - `VaultConnector.get_file_metadata()` (`connector.py:89-90`) hashes **raw file bytes** via `hashlib.sha1(content).hexdigest()` where `content = full_path.read_bytes()`
   - `MetadataExtractor._content_hash()` (`extractor.py:64`) hashes **parsed note content** via `hashlib.sha1(content.encode()).hexdigest()` where `content` is `note.content` (frontmatter stripped by the Markdown parser)
   - `MetadataStore.get_stale()` compares the stored hash (from the extractor) against the current hash (from the connector) — they **never match** because one includes frontmatter and the other doesn't
   - Result: every note was marked stale on every run, triggering a full re-extraction

2. **Missing usage tracking:**
   - `daily_sync.py:88` created `LLMClient()` with no `usage_store` parameter
   - All extraction LLM calls bypassed `usage.db` entirely
   - The admin dashboard only showed chat/inbox costs, hiding the real spend

## Fix Applied

1. **Hash override in `daily_sync.py`:** After `extractor.extract(note)` returns metadata, override `metadata.content_hash` with the raw-bytes hash from `current_hashes[path]` before upserting to the store. This ensures the stored hash matches what `get_stale()` compares against.

2. **Usage tracking:** Created a `UsageStore` in `extract_metadata()` and passed it to `LLMClient(usage_store=usage_store, usage_type="extraction")`.

3. **Configurable `usage_type` on `LLMClient`:** Added `usage_type` parameter to `__init__()` so different callers (inbox, extraction) are tracked separately in `usage.db`.

4. **Cost alert in admin API:** Added `today_cost`, `today_calls`, and `cost_alert` fields to `AdminStatsResponse`. Alert triggers when daily cost exceeds a configurable threshold (default $1.00).

5. **Frontend updates:** Added "Metadata Extraction" label to usage type breakdown, cost alert banner, and "Today's Cost" stat card.

## Files Modified

- `src/secondbrain/scripts/daily_sync.py` — Hash fix + UsageStore creation
- `src/secondbrain/scripts/llm_client.py` — Configurable `usage_type` parameter
- `src/secondbrain/api/admin.py` — Cost alert logic
- `src/secondbrain/models.py` — New `AdminStatsResponse` fields
- `frontend/src/components/admin/AdminDashboard.tsx` — Alert banner + extraction label + today stat
- `frontend/src/lib/types.ts` — TypeScript type updates
- `tests/test_daily_sync.py` — New: hash fix + usage tracking tests
- `tests/test_llm_client.py` — New: usage_type tests
- `tests/test_metadata_store.py` — New: hash consistency regression test
- `tests/test_admin_api.py` — New: cost alert tests

## How to Prevent

- **Always verify hash consistency end-to-end:** When two components produce hashes for comparison, they must hash the same input. Write a test that verifies round-trip: store a hash, then check `get_stale()` returns empty.
- **Every LLM call must have a UsageStore:** Treat `usage_store=None` as a code smell. Consider making it required or adding a warning log when it's missing.
- **Cost alerting:** The new threshold-based alert in the admin dashboard will catch future cost spikes immediately rather than waiting for a monthly bill review.
- **Tracing/observability:** Consider adding LangSmith or OpenTelemetry tracing to get full visibility into LLM call patterns, latency, and costs across all components.

## Lessons Learned

- **Silent cost bugs are the worst kind:** The system appeared to work correctly — extraction succeeded, metadata was stored, the dashboard showed low costs. The only signal was the Anthropic invoice.
- **Hash functions must be tested for agreement, not just correctness:** Both hash functions were individually correct — they just hashed different inputs. Testing either in isolation would pass.
- **Usage tracking is not optional:** Any code path that calls an LLM API must log to the usage store. The inbox processor had this right; the extraction pipeline was added later and missed it.
- **"All notes extracted" every run should have been a red flag:** The extraction log showed 35 notes extracted hourly, but none were changing. This signal was present in the logs but never investigated.

## Detection

Discovered during a manual review of the admin dashboard vs. actual Anthropic billing. The dashboard showed ~$0.03/day while the Anthropic invoice showed ~$8-10/day (~$300/month run rate). Investigation revealed extraction calls were not tracked in `usage.db` at all, and the hash mismatch was causing full re-extraction of all 35 notes every hour — 840 wasted Sonnet calls/day consuming 800K+ tokens.

**Earlier detection methods that would have caught this:**
- A cost alert threshold (now implemented)
- A log-level warning when `get_stale()` returns >50% of all notes
- Automated comparison of `usage.db` totals vs. API provider billing
- LLM call tracing showing the same notes being extracted repeatedly
