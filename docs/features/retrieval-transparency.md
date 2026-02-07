# Retrieval Transparency + Context-Aware Recency

> **Status:** Planned (Phase 5)
> **Estimated effort:** ~1 week
> **Depends on:** Phases 1-3 (done)

## Problem

When the system returns search results, the user has no visibility into _why_ a particular note was surfaced. This makes it hard to:
- Trust the results ("is this actually the best match?")
- Debug retrieval quality ("why isn't my note showing up?")
- Understand how recency plays into ranking

Additionally, when multiple versions of similar content exist (e.g., two grocery lists from different dates), the system has no mechanism to prefer the current one.

## Proposed Solution

### Score Breakdown in API Response

Add per-citation scoring to the `/ask` response:

```json
{
  "citations": [
    {
      "note_path": "...",
      "chunk_id": "...",
      "snippet": "...",
      "scores": {
        "lexical": 0.72,
        "vector": 0.85,
        "rerank": 0.91
      }
    }
  ]
}
```

### "Why This Result" in UI

Add an expandable section below each citation in the Next.js chat UI showing the score breakdown. Keep it collapsed by default so it doesn't clutter the normal experience.

### Context-Aware Recency (LLM-Driven)

Instead of a decay formula or scoring multiplier:

1. Pass note timestamps (`created_at`, `updated_at`) alongside chunk text to the LLM during synthesis
2. The LLM uses temporal context to reason about which information is current
3. Example: if two grocery lists are retrieved, the LLM naturally prefers the recent one because it has the dates

**Why LLM-driven instead of a scoring multiplier:**
- A decay multiplier would penalize foundational notes (decisions, specs, architecture)
- The LLM can reason about _what kind_ of note benefits from recency (a grocery list) vs. what doesn't (an architectural decision)
- No calibration needed; no risk of burying important old content

## Implementation Notes

- Score data is already computed internally during retrieval; this is mostly about exposing it
- Note timestamps are available from file metadata and SQLite
- The LLM prompt for synthesis needs a small addition: include `note_date` in the context window
- UI component: a small collapsible `<details>` or accordion below each citation

## What's Explicitly Excluded

- Time-decay scoring multiplier (replaced by LLM reasoning)
- Memory aging buckets (unnecessary abstraction)
- "On this day/week" resurfacing view (low impact)
- Any changes to the retrieval ranking algorithm itself

## Open Questions

- Should the score breakdown be visible in the API by default, or behind a `?debug=true` flag?
- How much timestamp context is useful to the LLM? Just `updated_at`, or also `created_at` + note folder path?
