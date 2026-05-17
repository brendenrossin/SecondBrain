---
type: concept
tags: [ai, infrastructure, cost]
created: 2026-03-19
updated: 2026-05-11
---

## Summary

LLM costs scale with tokens. Optimization is mostly about (a) sending fewer tokens, (b) using cheaper models where you can, and (c) caching aggressively. Most apps overspend by 5–10x before optimizing.

## Key Points

- **Prompt caching** is the single biggest win for repeated context. Anthropic and OpenAI both support it. ~90% cost reduction on cached prefix.
- **Model tiering** — use Haiku/4o-mini for classification, routing, summarization. Use Sonnet/4o only when the task actually needs it. Most apps default everything to the expensive model and burn budget.
- **Retrieval matters more than you think** — sending 8k tokens of relevant context is cheaper *and* better than sending 32k of mixed-quality context.
- **Streaming doesn't reduce cost** but it reduces perceived latency, which lets you get away with smaller context windows.

## Anti-patterns

- "Just send the whole document to the model." Works until your document is 200 pages and your bill is $20/query.
- Re-embedding on every request. Embeddings are cheap but not free; cache them.
- Calling the LLM to classify when a regex or small classifier would do.

## Practical numbers (mid-2026)

- Haiku: ~$0.25/$1.25 per Mtok (in/out)
- Sonnet: ~$3/$15 per Mtok
- 4o-mini: ~$0.15/$0.60 per Mtok
- Embeddings (text-embedding-3-small): ~$0.02 per Mtok

## Where this matters

- [[Pantry]] target: meal suggestion under $0.01/call. Hit it with Haiku + prompt caching.
- [[Lakeside Bank AI Advisory]] — their internal use cases need cost predictability. Recommend tiered routing.

## Related
- [[RAG fundamentals]]
- [[Async Python patterns]]
