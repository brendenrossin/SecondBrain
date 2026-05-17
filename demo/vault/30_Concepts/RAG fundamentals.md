---
type: concept
tags: [ai, retrieval, llm]
created: 2026-02-09
updated: 2026-05-10
---

## Summary

RAG (Retrieval-Augmented Generation) is a pattern for giving an LLM access to information it wasn't trained on — without retraining. The model retrieves relevant context from a corpus at query time and grounds its answer in that context.

The pattern: **embed → retrieve → rerank → generate.**

## Key Points

- **Embeddings** turn text into vectors. Similar meaning → similar vectors. Cosine similarity for distance.
- **Retrieval** finds top-k candidate chunks. Vector search is semantic; BM25 is lexical (exact terms). [[Hybrid retrieval]] combines both.
- **Reranking** uses a heavier model to score candidates more carefully. Worth the cost when the corpus is large.
- **Generation** is just calling the LLM with the retrieved context stuffed into the prompt. Quality of generation is bounded by quality of retrieval.

## Failure modes

- **Bad chunking** is the #1 killer. If your chunks are 200 tokens of random sentences, the embedding represents nothing in particular.
- **Embedding-only retrieval misses keyword matches.** "Northgate" the company name won't have a great vector unless you've seen it. BM25 catches it. Hybrid wins.
- **Hallucinated citations** — the model invents source attributions. Mitigation: force the model to quote verbatim, then validate the quote is in the retrieved context.
- **Stale corpus** — the index doesn't reflect recent changes. Need re-indexing pipeline.

## Where this matters

- [[Pantry]] uses RAG to match fridge contents to recipes.
- [[Lakeside Bank AI Advisory]] — RAG over policy docs is the strongest near-term bet for them.
- SecondBrain itself is a RAG system over a personal vault.

## Related
- [[Hybrid retrieval]]
- [[LLM cost optimization]]
