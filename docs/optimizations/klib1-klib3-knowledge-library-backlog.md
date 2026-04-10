# KLIB-1 + KLIB-3 Knowledge Library — Optimization Backlog

## Deferred from tri-review (2026-04-10)

### Low: Unbounded `_jobs` dict in wiki API
- **File:** `src/secondbrain/api/wiki.py:33`
- **Issue:** `_jobs: dict[str, IngestionJob] = {}` grows without bound. Every ingestion request adds a job that is never cleaned up.
- **Impact:** Negligible for single-user system. Would matter at scale.
- **Fix:** Add a TTL-based cleanup (e.g., evict jobs older than 1 hour) or cap dict size.

### Low: `get_vault_manifest()` not cached
- **File:** `src/secondbrain/api/dependencies.py:205-210`
- **Issue:** Unlike other dependency providers, `get_vault_manifest` is not `@lru_cache` decorated. It reads from disk on every call.
- **Impact:** Fast disk reads; manifest may legitimately change between calls. Inconsistent with pattern but functionally correct.
- **Fix:** Could add `@lru_cache` with a TTL wrapper, or accept as-is since the manifest updates after reindexing.
