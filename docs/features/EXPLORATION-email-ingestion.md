# Email Ingestion (Read-Only) — Feasibility Assessment

> **Status:** Assessed. On roadmap as Phase 10 (deprioritized 2026-02-15 — quick capture covers the gap; phases 8.5–9.5 deliver more daily value).
> **Original proposal:** Phase 8 in brainstorm roadmap
> **Decision date:** 2026-02-14
> **Full spec:** `docs/features/email-ingestion.md`

## Motivation

Index email subjects/snippets + minimal metadata to:
- Extract "needs reply" items and deadlines
- Surface people/entities mentioned in email alongside vault notes
- Present as signals (never auto-send)

## Open Questions — RESOLVED

### Integration approach
- **Decision:** Gmail API (direct, no MCP). `gmail.readonly` scope only.
- **What gets indexed:** Summary notes from LLM classification. Not raw email. Text-only (no HTML).
- **Threads:** Latest message only. Reply chains stripped. Thread reconstruction deferred.

### Privacy
- **Tokens:** `credentials.json` + `token.json` stored in `{data_path}/email/` (gitignored). OS keychain deferred — single-user local system.
- **Scopes:** `gmail.readonly` only. No write capability at any level.
- **Local processing:** Yes. Local embeddings (bge-base-en-v1.5). LLM classification can use local Ollama or Anthropic Haiku (cheap).

### Architecture
- **Chunking:** Email becomes a summary vault note (~100-300 words). Standard chunker handles it.
- **Embedding pipeline:** Works fine — emails are shorter than most vault notes.
- **Deduplication:** `source_id` (Gmail message ID) in frontmatter prevents re-processing.

### Maintenance
- **Token refresh:** Handled by `google-auth-oauthlib`. For personal `@gmail.com`, add yourself as a test user in OAuth consent screen for indefinite refresh tokens (no full verification needed).
- **Rate limits:** ~200-400 quota units/day vs 15,000/minute limit. Non-issue.
- **Incremental sync:** Timestamp-based. Tracked in `data/.email_sync_state`.

## Risks — ASSESSED

| Risk | Mitigation | Residual Risk |
|------|-----------|---------------|
| Prompt injection | Sandboxed LLM, spotlighting, constrained output schema, text-only, `gmail.readonly` | Low |
| Volume / bloat | Sender allowlist, `category:primary` filter, summary notes only, max 50/sync | Low |
| Cost | Local embeddings ($0), Haiku classification (~$0.15/month) | Negligible |
| OAuth complexity | One-time setup, auto-refresh, structured logging on failure | Low |

## Decision: Build

Low risk, low cost, clean architecture fit. See `docs/features/email-ingestion.md` for full spec.
