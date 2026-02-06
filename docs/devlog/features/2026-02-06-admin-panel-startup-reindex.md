# Feature: Admin Panel & Startup Reindex

**Date:** 2026-02-06
**Branch:** main

## Summary

Added a read-only Admin panel to the Gradio UI showing index stats (chunk counts, tracked files, last indexed time) and moved reindexing from per-query execution to UI startup. This prevents the UI from blocking during chat.

## Problem / Motivation

Reindexing inside the Gradio chat handler caused the UI to block for 180+ seconds (vs ~18s on CLI). The root cause was sentence-transformers holding the GIL inside Gradio's thread pool, combined with ChromaDB single-process contention. There was also no visibility into indexing status from the UI.

## Solution

1. **Admin panel**: Collapsible accordion (below Sources) with a markdown table showing vector/lexical chunk counts, tracked file count, and last indexed timestamp. Includes a "Refresh Stats" button.
2. **Startup reindex**: Moved `check_and_reindex()` from the `chat_stream()` generator to `main()`, before `demo.launch()`. This runs outside Gradio's thread pool with no threading contention.
3. **Performance metrics moved to Admin**: The per-query latency table (retrieval/reranking/generation times) was relocated from the Sources accordion to the Admin panel, keeping Sources focused on citations.

## Files Modified

- `src/secondbrain/stores/index_tracker.py` — Added `get_stats()` method (file_count, total_chunks, last_indexed_at)
- `src/secondbrain/ui.py` — Added Admin accordion, `get_index_status()` helper, moved reindex to startup, moved performance metrics to admin panel, removed "Reindex Now" button and `do_reindex_now()` helper

## Key Decisions & Trade-offs

- **Removed "Reindex Now" button**: The button blocked the UI for minutes. Reindex now only happens at startup — users restart the UI to pick up new index data. This is predictable and avoids all threading issues.
- **Removed per-query `check_and_reindex()`**: The trigger file from `daily_sync` is now consumed at startup, not during chat. Trade-off: vault changes aren't reflected until UI restart.
- **No background thread reindex**: Considered running reindex in a background thread, but sentence-transformers holds the GIL, so it would still degrade chat performance. Startup-only is the cleanest approach given the single-process ChromaDB constraint.
- **Performance metrics in Admin, not Sources**: Keeps the Sources accordion clean (citations only) and groups all operational info together.

## Patterns Established

- **Admin accordion pattern**: Read-only operational info in a collapsed accordion, refreshed on demand via button. Future admin features (e.g., query logs, cache stats) should go here.
- **Startup-only expensive operations**: CPU-bound or GIL-holding work should run before `demo.launch()`, never inside Gradio event handlers.

## Testing

- 122 unit tests pass (no new tests needed — admin panel is UI-only)
- Manual verification: daily_sync writes trigger, UI startup consumes it, admin stats display correctly, chat is responsive, performance metrics update after queries

## Future Considerations

- The daily_sync log message still says "UI will reindex on next query" — minor wording issue, should say "on next UI restart"
- If vault grows large, startup reindex could delay UI availability. Could add a progress indicator or move to OpenAI embeddings (API calls, no model loading).
- Vector chunks (49) vs Lexical chunks (37) discrepancy suggests some chunks exist in ChromaDB but not in the lexical store — may warrant investigation
