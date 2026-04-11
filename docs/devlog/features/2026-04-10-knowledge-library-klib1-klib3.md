# Feature: Knowledge Library MVP (KLIB-1 + KLIB-3)

**Date:** 2026-04-10
**Branch:** feature/klib1-klib3-knowledge-library
**PR:** [#7](https://github.com/brendenrossin/SecondBrain/pull/7)

## Summary

Added external content ingestion and compounding wiki save to SecondBrain. Users can drop a URL (web article, YouTube video, or PDF) into Quick Capture and get a structured, LLM-compiled Obsidian wiki page written to their vault. Chat answers that synthesize multiple sources show a "Save as wiki page" chip for one-click conversion. Inspired by Karpathy's LLM Wiki pattern.

## Problem / Motivation

SecondBrain only knew about content already in the vault. External knowledge (articles, videos, papers) required manual note-taking. Similarly, high-quality synthesized answers from the chat were ephemeral — lost after the conversation ended. Both represented missed opportunities to compound the knowledge base over time.

## Solution

### KLIB-1: External Content Ingestion
Full pipeline: URL input -> content type detection -> fetch (readability-lxml for web, yt-dlp for YouTube transcripts, pymupdf4llm for PDFs) -> three-layer safety audit (Sonnet) -> LLM compilation into structured wiki page (Haiku) -> write to `Wiki/` folder -> reindex.

### KLIB-3: Compounding Query Loop
After each `/ask` or `/ask/stream` response, a scoring function evaluates whether the answer is worth saving (PASS retrieval, 3+ distinct citation sources, minimum length, factual-query heuristic). Eligible answers show a "Save as wiki page" UI chip that triggers `WikiCompiler.compile_answer` to restructure the conversational response into a reference-quality Obsidian note.

## Files Modified

### New package: `src/secondbrain/ingestion/`
- `fetcher.py` — Content type detection + fetch dispatch (web, YouTube, PDF)
- `safety.py` — Three-layer hardened safety auditor (XML delimiters, forced tool_use, tool_result message pattern)
- `compiler.py` — LLM-powered wiki page generator with frontmatter, source attribution, [[wiki-links]]
- `pipeline.py` — Orchestrator: fetch -> audit -> duplicate check -> compile -> write -> index

### API layer
- `api/wiki.py` — POST /wiki/ingest (background job), GET /wiki/ingest/{job_id} (poll), POST /wiki/save (answer->wiki), wiki suggestion scoring
- `api/dependencies.py` — Added `get_safety_auditor()`, `get_wiki_compiler()` singletons
- `api/ask.py` — Wired `compute_wiki_suggestion` into /ask and /ask/stream responses
- `models.py` — WikiIngestRequest/Response, WikiSaveRequest/Response, WikiSuggestion, WikiJobStatusResponse

### Frontend
- `CaptureForm.tsx` — URL input card with content type badge, progress stages, safety audit feedback
- `ChatMessage.tsx` — "Save as wiki page" chip on eligible assistant messages
- `ChatMessages.tsx` — Passes wikiSuggestion/conversationId/lastQuery to messages
- `ChatProvider.tsx` — Tracks wikiSuggestion and lastQuery state from SSE done events
- `api.ts` — wikiIngest, wikiIngestStatus, wikiSaveAnswer functions
- `types.ts` — WikiIngestResponse, WikiJobStatusResponse, WikiSaveResponse, WikiSuggestion interfaces

### Tests (6 new files)
- `test_fetcher.py` — URL detection, FetchedContent dataclass
- `test_safety_auditor.py` — Chunking, audit results, API mock, batch rejection, usage logging
- `test_wiki_compiler.py` — Compile frontmatter, vault manifest injection, answer compilation, duplicate detection
- `test_ingestion_pipeline.py` — Full pipeline success/failure, safety blocking, index callback, filename collision
- `test_wiki_api.py` — Wiki suggestion scoring logic (eligibility, factual heuristics, deduplication)

## Key Decisions & Trade-offs

1. **Safety auditor uses Sonnet (not Haiku)** — Security-critical classification warrants a stronger model. Cost is ~$0.01-0.02 per document, negligible at personal ingestion volumes. Three-layer hardening (XML delimiters, structured tool_use output, tool_result message pattern) makes it robust against prompt injection in fetched content.

2. **Compiler uses Haiku** — Wiki page generation is creative but not security-sensitive. Haiku is fast and cheap, ideal for restructuring already-audited text.

3. **Background job with polling, not WebSocket** — Ingestion takes 10-30 seconds. A simple poll-every-second pattern is simpler than WebSocket and works fine for single-user. Jobs are ephemeral (in-memory dict with TTL eviction).

4. **Duplicate overwrite, not append** — Re-ingesting the same URL overwrites the existing wiki page via `find_existing_by_source` frontmatter matching. This keeps the Wiki folder clean.

5. **Wiki suggestion scoring is heuristic-based** — No LLM call needed. Simple rules: PASS retrieval, 3+ unique citation sources, minimum character length, factual-query filter. Cheap and deterministic.

6. **YAML frontmatter escaping** — Added `_escape_yaml_str()` to handle double quotes in titles/URLs that would break YAML parsing. Caught during tri-review.

## Patterns Established

- **`src/secondbrain/ingestion/` package** — New top-level package for external content processing. Future ingestion sources (email, RSS, etc.) should follow the same fetch -> audit -> compile -> write pattern.
- **Safety auditor as mandatory gate** — All external content must pass through `SafetyAuditor` before entering the vault. Fail-closed design (API errors = content blocked).
- **Background job pattern** — `asyncio.create_task` + in-memory job dict + polling endpoint. Suitable for short-lived background work in single-user context.
- **Wiki suggestion scoring** — Lightweight eligibility check on answers. Can be extended with more heuristics without adding LLM cost.

## Testing

- 665 tests passing (all pre-existing + new)
- Tri-review: 5 findings (1 High, 2 Medium, 2 Low), all fixed
- Manual testing needed: URL ingestion (web, YouTube, PDF), wiki save chip in chat

## Future Considerations

- **KLIB-2** (Vault lint/health checks) and **KLIB-4** (AI research mode) remain on the roadmap
- The safety auditor could be extended with a blocklist/allowlist for known-safe/blocked domains
- Large PDFs may hit the 10MB limit; could add chunked PDF processing
- The `_jobs` dict has TTL eviction but could benefit from persistent storage if job history becomes valuable
- `find_existing_by_source` scans all wiki files linearly; could index source URLs if the wiki folder grows large
