---
type: note
tags: [research, ai, retrieval]
created: 2026-05-06
updated: 2026-05-13
---

## Summary

Writing this up because Lakeside is going to ask me hard questions at the working session and I want crisp intuitions, not handwaving.

## Why hybrid wins

Most queries fall into one of two failure modes for single-method retrieval:

1. **Vague intent + specific terms.** "What's our policy on overdraft fees for new accounts?" — "overdraft" and "new accounts" are exact terms BM25 nails. Vectors get distracted by "policy" matching everything.
2. **Specific intent + vague terms.** "How do I avoid burnout?" — vectors find adjacent concepts ("sustainable engineering culture") that BM25 misses entirely.

Hybrid covers both. Cost is one extra search.

## When it's not worth it

- Single-domain corpora where the vocabulary is fixed and shared (e.g. medical codes). BM25 is enough.
- Sub-100-doc corpora. Just use whatever.

## My take for Lakeside

Their policy corpus is mid-size (~5k docs) with high vocabulary variance (legal language vs. employee questions). **Hybrid is the right default.** Don't even debate it.

The interesting question is whether to add learned reranking on top. For their pilot, I'd say no — start simple, measure, add complexity when there's evidence.

## Related
- [[Hybrid retrieval]]
- [[RAG fundamentals]]
- [[Lakeside Bank AI Advisory]]
