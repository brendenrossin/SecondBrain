---
type: concept
tags: [ai, retrieval, search]
created: 2026-03-02
updated: 2026-05-13
---

## Summary

Hybrid retrieval = BM25 (lexical/keyword) + vector search (semantic), with results merged via Reciprocal Rank Fusion (RRF) or a learned reranker. It consistently outperforms either method alone on real corpora.

## Key Points

- **BM25** handles exact-term matches. "ROI" beats "return on investment" if the query says "ROI." Vector search often misses this — the embedding for "ROI" is mediocre because it's a short acronym.
- **Vector search** handles semantic similarity. "How do I prevent burnout in my team?" matches a note titled "Sustainable engineering culture" even with zero overlapping words.
- **RRF** is the simplest fusion: for each result, score = sum of (1 / (k + rank)) across both ranking lists. k=60 is a good default. No tuning needed.
- **Learned rerankers** (cross-encoders) score query+result jointly and beat RRF by a meaningful margin — but cost more per query.

## Intuitions

- Short queries (1–3 words): BM25 often wins. Vector search has too little signal.
- Long, intent-heavy queries ("what should I focus on this week?"): vector wins.
- Most real-world queries: hybrid beats both, often by 10–20% on recall@10.

## Where this matters

- SecondBrain uses BM25 (SQLite FTS5) + vectors (ChromaDB) + RRF + LLM reranker.
- [[Lakeside Bank AI Advisory]] — they will need hybrid retrieval for their policy doc search. BM25-only won't catch synonyms; vector-only won't catch policy codes.
- [[Pantry]] uses lightweight hybrid — BM25 on ingredient names, vectors on flavor profile.

## Related
- [[RAG fundamentals]]
- [[LLM cost optimization]]
