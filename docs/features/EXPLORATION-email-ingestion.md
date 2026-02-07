# Email Ingestion (Read-Only) — Feasibility Assessment

> **Status:** Not committed. Requires feasibility assessment before entering roadmap.
> **Original proposal:** Phase 8 in brainstorm roadmap
> **Decision date:** 2026-02-07

## Motivation

Index email subjects/snippets + minimal metadata to:
- Extract "needs reply" items and deadlines
- Surface people/entities mentioned in email alongside vault notes
- Present as signals (never auto-send)

## Open Questions (Must Answer Before Building)

### Integration approach
- Gmail API (OAuth, token refresh, scope management) vs IMAP vs MCP?
- What gets indexed? Subject + snippet only? Full body? Attachments?
- How to handle threads vs individual messages?

### Privacy
- Where are OAuth tokens stored? (Must be OS keychain, not file)
- What scopes are needed? (Minimum: read-only, no send)
- Can email content be processed locally without sending to cloud LLM?

### Architecture
- How does email chunking differ from note chunking? (Short messages, threads, quoted text)
- Does the existing embedding pipeline handle email-length text well?
- How to deduplicate information that appears in both email and vault notes?

### Maintenance
- Token refresh handling (Gmail tokens expire)
- Rate limits on email APIs
- Incremental sync (only new emails since last check)

## Risks

- **Scope creep:** Email is a massive, noisy data source. Without aggressive filtering, it could overwhelm the signal-to-noise ratio.
- **Privacy:** Indexing email is a significant escalation from indexing personal notes. Needs careful scoping.
- **Maintenance burden:** OAuth token management, API changes, and rate limits add ongoing operational cost.

## Decision: Build / Defer / Kill

Not yet decided. Needs a focused spike (1-2 days) to evaluate the integration approach before committing.
