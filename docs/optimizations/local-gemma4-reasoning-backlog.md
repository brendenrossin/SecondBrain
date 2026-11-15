# Local Gemma 4 Reasoning — Optimization Backlog

Deferred findings from the tri-review of `fix/local-gemma4-reasoning` (2026-11-15).

| # | Severity | Confidence | Location | Finding | Suggested fix |
|---|----------|------------|----------|---------|---------------|
| 1 | Low | 1/3 (Architect) | `src/secondbrain/retrieval/reranker.py` `local_extra_body` | Request-building helper for all local LLM calls lives in the reranker module; the answerer and LLM client import it from there. | Move to a small `secondbrain/llm_options.py` if a third or fourth caller appears. |
| 2 | Low | 1/3 (Architect) | Ollama server config (not in repo) | Ollama's default `keep_alive` is 5 minutes, so after a short idle both local models (~17 GB) are evicted and the next phone query pays a cold load. | Set `OLLAMA_KEEP_ALIVE` (e.g. `30m`) in Ollama's launch environment, or pass `keep_alive` per request. |
| 3 | Low | 1/3 (Auditor) | `src/secondbrain/scripts/llm_client.py` Ollama branch | An empty `content` string is treated as success, so it never falls through to the OpenAI fallback. | Treat empty content as a failure and fall through. |
