# Inbox Processing Upgrade, Anthropic Model Migration & Note Matching

> **Status:** Planned (Phase 5.5)
> **Estimated effort:** 3-5 days (Work Items 1-4; vault health deferred)
> **Depends on:** Phases 1-3 (done), daily sync pipeline (done), Next.js frontend (done)

## Problem

Three related issues with the current inbox processing and chat pipeline:

### 1. Segmentation too conservative for dictated notes
The inbox processor receives voice-dictated, stream-of-consciousness text from Wispr Flow. The current segmentation prompt says "only split when topics are clearly distinct" and "when in doubt, keep content together." This causes related-but-distinct topics to get merged into a single note. Real example: Rachel's birthday gift ideas and her parents' travel plans got combined into one note about "Rachel's Birthday Travel Plans" because they both involve Rachel. These are separate concerns that a user would search for independently.

### 2. Model quality insufficient for complex classification
Inbox processing (segmentation + classification) is the hardest LLM task in the system. It currently uses Ollama (`gpt-oss:20b`) with GPT-4o-mini fallback. A stronger model would produce better segmentation of messy dictated text and more accurate classification/routing. The chat pipeline (reranker + answerer) also uses GPT-4o-mini, which could be upgraded.

### 3. New content always creates new files
The inbox processor always creates a new file for non-daily notes (except for two hardcoded "living documents": Grocery List and Recipe Ideas). If a user dictates something about an existing topic (e.g., more thoughts about a project that already has a note), a second file is created instead of appending to the existing one. Over time this creates topic fragmentation, which degrades retrieval quality by splitting related content across files.

## Solution

Five work items organized into 7 implementation steps:

### Work Item 1: Segmentation Prompt Rewrite

**Goal:** Better splitting of voice-dictated text with subtle topic transitions.

**Approach:**
- Reframe the splitting heuristic around **retrieval**: "Would you search for these topics separately?" instead of "are these clearly distinct?"
- Add **dictation-aware guidance**: explicitly tell the model that input is voice-transcribed stream-of-consciousness where topic transitions lack paragraph breaks or headers
- Handle the **"same person, different concerns"** case: two segments about Rachel are still two segments if the concerns are unrelated (birthday gifts vs. parents visiting)
- Add **3 few-shot examples** showing correct splits for dictated text:
  1. Birthday gifts + parents' travel plans (same person, 2 segments)
  2. Work meeting update + personal learning goal (different domains, 2 segments)
  3. Grocery list + kitchen equipment thought (related context, 1 segment)

**File:** `src/secondbrain/scripts/inbox_processor.py` (replace `SEGMENTATION_PROMPT` constant)

### Work Item 2: Claude Sonnet 4.5 for Inbox Processing

**Goal:** Use a stronger model for the hardest LLM task in the system.

**Approach:**
- Add `anthropic` Python SDK as a dependency
- Extend `LLMClient` with Anthropic as the **primary** provider for inbox processing
- Fallback chain: **Anthropic (Sonnet 4.5) → Ollama → OpenAI (GPT-4o-mini)**
- New config settings: `SECONDBRAIN_ANTHROPIC_API_KEY`, `SECONDBRAIN_INBOX_MODEL`, `SECONDBRAIN_INBOX_PROVIDER`

**Key technical detail:** Anthropic's API is NOT OpenAI-compatible. Uses `client.messages.create(model=..., system=..., messages=[...])` with `system` as a separate parameter. Response is `response.content[0].text` (TextBlock).

**Files:**
- `pyproject.toml` — add `anthropic>=0.40.0`
- `src/secondbrain/config.py` — add Anthropic settings
- `src/secondbrain/scripts/llm_client.py` — add Anthropic provider

**Model and pricing:**

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Use case |
|-------|----------------------|----------------------|----------|
| GPT-4o-mini (current) | $0.15 | $0.60 | — |
| Claude Sonnet 4.5 | $3.00 | $15.00 | Inbox processing |
| Claude Haiku 4.5 | $0.80 | $4.00 | Chat (reranker + answerer) |

At the expected volume (~0-5 inbox notes/day, ~5-10 chat queries/day), monthly cost is well under $5.

### Work Item 3: Claude Haiku 4.5 for Chat (Reranker + Answerer)

**Goal:** Better chat quality by replacing GPT-4o-mini with Claude Haiku 4.5.

**Approach:**
- Add `provider` parameter to `LLMReranker` and `Answerer` classes (`"anthropic"` or `"openai"`)
- Anthropic non-streaming: `client.messages.create(...)` for reranker scoring
- Anthropic streaming: `client.messages.stream(...)` context manager → iterate `stream.text_stream` to yield tokens for answer generation
- Keep existing OpenAI SDK path for Ollama (which uses OpenAI-compatible API)
- Update factory functions in `dependencies.py` to wire Anthropic as the cloud provider
- Update frontend provider toggle: rename "OpenAI" → "Cloud", change provider value from `"openai"` to `"anthropic"`

**Files:**
- `src/secondbrain/retrieval/reranker.py` — add Anthropic dispatch
- `src/secondbrain/synthesis/answerer.py` — add Anthropic dispatch + streaming
- `src/secondbrain/api/dependencies.py` — wire Anthropic to factory functions
- `src/secondbrain/models.py` — update `AskRequest.provider` default
- `frontend/src/components/chat/ProviderToggle.tsx` — rename button
- `frontend/src/components/providers/ChatProvider.tsx` — update types + localStorage migration
- `frontend/src/lib/types.ts` — update type

### Work Item 4: Note Matching During Classification

**Goal:** Route new content to existing notes when the topic already has a note, instead of always creating duplicates.

**Approach:**
- Before classification, gather existing note titles from `10_Notes/`, `20_Projects/`, `30_Concepts/` (capped at 75 per folder)
- Pass titles to the LLM during classification as context: `"Existing notes: [10_Notes] Rachel Birthday, [10_Notes] Grocery List, [20_Projects] SecondBrain, ..."`
- Add `"existing_note"` field to classification JSON output — filename to append to, or null for new note
- When `existing_note` is set: load existing file, append new content under a `### YYYY-MM-DD` date heading, update `updated` frontmatter field
- This **generalizes** the living document concept to all notes

**Safeguards:**
- LLM instructed to "only match when CONFIDENT — a wrong match is worse than creating a new note"
- Does NOT apply to `daily_note` or `living_document` types (those have their own routing)
- Fallback: if referenced file doesn't exist on disk, create a new note instead
- Title list capped at 75 per folder to keep prompt size reasonable (~500-1000 tokens)
- Original inbox file always archived to `_processed/` — nothing is lost

**File:** `src/secondbrain/scripts/inbox_processor.py`

### ~~Work Item 5: Vault Health Check Foundation~~ (Deferred)

> **PM Decision (2026-02-08):** Deferred. Premature with ~16 notes. "Warn when folder exceeds 50 notes" — we're at ~5. "Similar titles" — visible at a glance with this vault size. Revisit when the vault reaches 100+ notes and organic duplication becomes a real problem. The note matching in Work Item 4 prevents the duplication that would make health checks necessary.

## Implementation Order & Dependencies

```
Step 1: SDK + Config (foundation)
├── Step 2: Segmentation prompt rewrite (independent — no SDK needed)
├── Step 3: LLMClient Anthropic support (inbox)
│   └── Step 5: Note matching (benefits from smarter model)
└── Step 4: Reranker + Answerer Anthropic support (chat)
    └── Step 5: Frontend toggle update
```

Each step leaves the system in a working state. Step 2 can be done in parallel with everything else.

## Files Modified/Created

| File | Steps | Action |
|------|-------|--------|
| `pyproject.toml` | 1 | Add `anthropic` dependency + mypy override |
| `src/secondbrain/config.py` | 1 | Add Anthropic settings, update model defaults |
| `src/secondbrain/scripts/inbox_processor.py` | 2, 5 | Rewrite segmentation prompt, add note matching |
| `src/secondbrain/scripts/llm_client.py` | 3 | Add Anthropic to fallback chain |
| `src/secondbrain/retrieval/reranker.py` | 4 | Add Anthropic provider support |
| `src/secondbrain/synthesis/answerer.py` | 4 | Add Anthropic provider + streaming |
| `src/secondbrain/api/dependencies.py` | 4 | Wire Anthropic to factory functions |
| `src/secondbrain/models.py` | 4 | Update AskRequest |
| `frontend/.../ProviderToggle.tsx` | 5 | Rename "OpenAI" → "Claude" |
| `frontend/.../ChatProvider.tsx` | 5 | Update provider type + localStorage migration |
| `frontend/src/lib/types.ts` | 5 | Update AskRequest type |

## What's Explicitly Excluded (and Why)

| Excluded | Rationale |
|----------|-----------|
| **Vault health checks** | Premature with ~16 notes. Deferred until vault reaches 100+ notes. Note matching (Work Item 4) prevents the duplication that would make health checks necessary. |
| **Full vault reorganization UI** | Too complex for v1. Revisit when health checks are eventually built. |
| **Automatic note merging** | Violates "suggestion-only" principle. |
| **Embedding-based note matching** | LLM-based title matching during classification is simpler, cheaper, and already in the loop. Embedding similarity would require an extra search step. |
| **OpenAI → Anthropic migration for metadata extraction** | Metadata extraction uses the same `LLMClient`, so it gets Anthropic support automatically via Step 3. No separate work needed. |
| **Removing OpenAI SDK dependency** | Still needed for Ollama (OpenAI-compatible API) and as a fallback provider. |

## Testing Strategy

**Automated:**
- All 174 existing tests continue to pass (they mock LLM calls)
- New tests for `_get_existing_titles`, `_append_to_existing_note`, `_validate_classification` with `existing_note`
- New tests for Anthropic provider paths in `LLMClient`, `LLMReranker`, `Answerer`

**Manual QA:**
- Drop multi-topic dictation in Inbox → verify correct segmentation
- Drop note about existing topic → verify it appends to existing note
- Send chat query → verify response comes from Claude Haiku 4.5
- Verify frontend toggle works for both providers

## Design Decisions (Resolved)

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Vault health scope** | Deferred entirely. | Premature with 16 notes. Note matching prevents the duplication problem. Revisit at 100+ notes. |
| **Note matching for projects** | Restrict to `10_Notes/` and `30_Concepts/` only. | Project notes have structured content (objectives, milestones) where appending is less clean. Wrong match into a project file is more damaging than a duplicate. |
| **Provider toggle naming** | "Claude" — not "Cloud" or "Anthropic". | Specific, recognizable brand name. Users know what Claude is. "Cloud" is vague. "Anthropic" is the company, not the product. |
