# Feature: Anthropic Migration + Inbox Upgrade

**Date:** 2026-02-09
**Phase:** 5.5

## Summary

Migrated the LLM provider stack from OpenAI-first to Anthropic-first across the entire system. Sonnet 4.5 powers inbox processing, Haiku 4.5 handles chat reranking and answer synthesis. Also added note matching to prevent vault fragmentation when dictated content relates to existing notes.

## Problem / Motivation

The system was hardcoded to OpenAI (gpt-4o-mini) for reranking/synthesis and Ollama-first for inbox processing. Anthropic Claude models offer better instruction following for structured tasks like segmentation and classification. Additionally, the inbox processor would always create new notes even when content clearly related to an existing note, causing vault fragmentation over time.

## Solution

1. **Anthropic SDK integration** across three layers: LLMClient (inbox), LLMReranker (chat), and Answerer (chat)
2. **3-way provider dispatch** in the API: Anthropic (default) / OpenAI / Local (Ollama)
3. **If/else branching** per provider (no abstract interface) — only 2 real code paths since Ollama reuses OpenAI's SDK
4. **Note matching** during classification: scans `10_Notes/` and `30_Concepts/` for existing titles, injects them into the classification prompt, and appends to matching notes instead of creating duplicates
5. **Improved segmentation prompt**: reframed around "would you search for these topics separately?" with 3 few-shot examples

## Files Modified

**Config & Dependencies:**
- `pyproject.toml` — +anthropic SDK dependency, +mypy override
- `src/secondbrain/config.py` — +anthropic_api_key, +inbox_model/provider, model defaults changed to Haiku 4.5

**LLM Client (inbox processing):**
- `src/secondbrain/scripts/llm_client.py` — Anthropic-first fallback chain (Anthropic -> Ollama -> OpenAI)
- `src/secondbrain/scripts/inbox_processor.py` — New segmentation prompt, +_get_existing_titles(), +_append_to_existing_note(), existing_note field in classification, updated routing logic

**Chat/Retrieval:**
- `src/secondbrain/retrieval/reranker.py` — +provider param, Anthropic branch in _score_candidates_batch()
- `src/secondbrain/synthesis/answerer.py` — +provider param, Anthropic branches for answer() and answer_stream()
- `src/secondbrain/api/dependencies.py` — Factory functions for all 3 providers (get_reranker/get_openai_reranker/get_local_reranker, same for answerer)
- `src/secondbrain/api/ask.py` — 3-way provider dispatch in both /ask and /ask/stream
- `src/secondbrain/models.py` — AskRequest.provider default changed to "anthropic"

**Frontend:**
- `frontend/src/lib/types.ts` — Provider union type updated
- `frontend/src/components/providers/ChatProvider.tsx` — 3-way Provider type, localStorage migration (old "openai" -> "anthropic")
- `frontend/src/components/chat/ProviderToggle.tsx` — 3-button toggle: Claude / Local / OpenAI

**Tests:**
- `tests/test_inbox_processor.py` — +TestGetExistingTitles, +TestAppendToExistingNote, +TestValidateClassificationWithExistingNote
- `tests/test_llm_client.py` — New file: Anthropic success, fallback on failure, no-key skip

## Key Decisions & Trade-offs

| Decision | Rationale |
|----------|-----------|
| If/else dispatch, no abstract interface | Only 2 real SDK paths. An ABC would be over-engineering for 2 providers where one (Ollama) reuses the other's SDK. |
| Fallback chain order: Anthropic -> Ollama -> OpenAI | Anthropic is highest quality, Ollama is local/free, OpenAI is last resort. For inbox this ensures best segmentation quality. |
| Note matching scoped to 10_Notes/ + 30_Concepts/ only | Projects (20_Projects/) have structured content with auto-synced sections; matching them risks corruption. |
| localStorage migration: old "openai" -> "anthropic" | Existing users get auto-migrated to the new default without losing their preference if they explicitly chose "local". |
| Anthropic uses `system` param, not system message | Anthropic API separates system prompt from messages, unlike OpenAI. This is cleaner and avoids role confusion. |

## Patterns Established

- **Provider branching pattern**: `if self.provider == "anthropic": ... else: ...` in reranker/answerer. Future providers should follow this pattern.
- **Factory function naming**: `get_reranker()` (default/Anthropic), `get_openai_reranker()`, `get_local_reranker()` — explicit names, all @lru_cache.
- **Note matching in inbox**: `_get_existing_titles()` collects titles, injected into classification prompt's user message, `existing_note` field checked before normal routing.

## Testing

- 200 tests pass (including 11 new tests)
- Lint clean (ruff), type clean (mypy strict)
- Manual verification needed: add `SECONDBRAIN_ANTHROPIC_API_KEY` to `.env`, restart backend, test chat with all 3 providers, test inbox with dictation note

## Future Considerations

- **Token cost monitoring**: Haiku 4.5 for every rerank + answer call could add up; may want usage tracking
- **Note matching quality**: The title list approach is simple but limited; future could use embeddings for semantic matching
- **Streaming difference**: Anthropic streaming uses context manager (`with client.messages.stream()`), OpenAI uses iterator — these behave slightly differently on error
