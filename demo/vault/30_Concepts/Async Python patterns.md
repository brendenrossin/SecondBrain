---
type: concept
tags: [python, performance]
created: 2026-04-02
updated: 2026-05-09
---

## Summary

Async Python is great for IO-bound concurrency and terrible for CPU-bound work. The two failure modes that actually matter in real services: (1) accidentally blocking the event loop with sync IO, (2) treating async like threads.

## Key Points

- **Event loop blocks on sync IO.** `requests.get()` in an async handler blocks every other concurrent request. Use `httpx.AsyncClient` or wrap with `asyncio.to_thread()`.
- **`asyncio.to_thread()`** is the easy fix for legacy sync code in async handlers. It dispatches to a thread pool — no rewrite required.
- **`asyncio.gather()`** runs awaitables concurrently. Pair with `return_exceptions=True` so one failure doesn't kill the batch.
- **Timeouts everywhere.** Async makes it easy to forget — and a hung HTTP call freezes one task forever. Wrap external calls in `asyncio.timeout()`.

## Practical patterns

```python
# Wrap sync IO
result = await asyncio.to_thread(blocking_function, arg)

# Parallel fan-out with timeout
async with asyncio.timeout(30):
    results = await asyncio.gather(
        fetch_a(), fetch_b(), fetch_c(),
        return_exceptions=True,
    )
```

## Anti-patterns

- `time.sleep()` in async code. Use `await asyncio.sleep()`.
- `requests` library anywhere in an async path.
- Sharing an `httpx.AsyncClient` across requests but never closing it (resource leak).

## Where this matters

- [[Pantry]] backend — LLM calls + recipe DB queries are all IO. Async is the right choice.
- SecondBrain itself — without `asyncio.to_thread()` on the embedding/retrieval paths, one slow query blocks the entire API.

## Related
- [[LLM cost optimization]]
