---
type: note
tags: [research, ai, retrieval]
created: 2026-04-26
updated: 2026-05-11
---

## Summary

Ongoing scratch notes as I read papers and posts on RAG patterns. Filtering for what's actually useful in production, not benchmark theater.

## What's holding up in production

- **Contextual retrieval (Anthropic, 2024)** — prepend a per-chunk summary before embedding. Reported ~35% reduction in retrieval failures. Verified on Pantry — modest but real win.
- **Reciprocal Rank Fusion** for hybrid — boring, dependable, no tuning. Hard to beat without learned reranking.
- **Cross-encoder reranker** after RRF — adds latency but improves quality meaningfully on long-tail queries.

## What's overhyped

- "Agent" RAG with iterative retrieval. Sometimes wins, often just adds latency and cost without quality gains. Useful for *complex multi-step questions*, not most queries.
- Vector DB benchmarks. The differences between ChromaDB / Qdrant / pgvector at most app sizes are noise. Pick whatever's easiest to operate.
- "Long context will kill RAG." It won't. Retrieval is cheaper, faster, and more debuggable.

## Open Qs

- When does query rewriting actually help? My sense: only when users phrase questions in vague natural language. For tight, keyword-heavy queries it's neutral or harmful.
- How much chunk overlap matters? Most apps overdo it. 10–15% is plenty.

## Related
- [[RAG fundamentals]]
- [[Hybrid retrieval]]
- [[Lakeside Bank AI Advisory]]
