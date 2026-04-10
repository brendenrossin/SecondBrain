# TRACE-1 Optimization Backlog

Low-priority items from tri-review. Address if they become relevant.

| # | File:Line | Severity | Finding | Notes |
|---|-----------|----------|---------|-------|
| 1 | `tracing.py:33` | Low | `json.dumps(json.loads(...))` round-trip for compact output | Microseconds vs seconds for LLM calls. Not worth optimizing. |
| 2 | `tracing.py:39-40` | Low | `shutdown()` is empty | `BatchSpanProcessor` handles flush before shutdown. Acceptable. |
| 3 | `test_tracing.py:106-123` | Low | AST/string-based integration tests are fragile | Pragmatic for single-user project. Replace if they break often. |
| 4 | `tracing.py:31` | Low | File opened/closed per export batch | Infrequent writes, not worth persistent handle complexity. |
