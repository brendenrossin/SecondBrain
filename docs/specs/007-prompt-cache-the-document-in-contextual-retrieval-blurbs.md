---
id: '007'
title: Prompt-cache the document in contextual retrieval blurbs
project: second-brain
tier: quick
status: Implemented
version: 0.1.0
created: '2026-11-22'
updated: '2026-11-22'
tags: []
history:
- status: Draft
  date: '2026-11-22'
  note: created
- status: Approved
  date: '2026-11-22'
  note: gate passed
- status: Implemented
  date: '2026-11-22'
  note: gate passed
---
# 007 — Prompt-cache the document in contextual retrieval blurbs

## Intent
Contextual retrieval (`indexing/context.py`) makes one Haiku 4.5 call per chunk, and each call
sends the **whole note** with no prompt caching. So the cost of a note grows with its number of
chunks times its length.

Once spec 001 indexed `Witt/`, long spec mirrors (50–131 KB, about 12k–33k tokens) made this the
whole bill:
- `context_generation` cost $9.75 between 2026-11-21 and 2026-11-22. November's total is $10.45,
  against $0.12 in October.
- The most expensive single run was 98 calls × 24k tokens = $2.40.
- The spend hit the Anthropic workspace usage limit on 2026-11-22, and every Anthropic call has
  failed since then, until 2026-12-01.

"Fixed" means three things:
- The document becomes a cached prompt prefix, written once per note at 1.25× and read by every
  later chunk call at 0.1×. That cuts input cost on long notes by about 85–90%.
- The logged cost reflects cache pricing, so the admin dashboard shows the real number.
- Blurb output is unchanged: same model, same system prompt, same instruction text.

Haiku 4.5's minimum cacheable prefix is 4096 tokens. Shorter notes silently don't cache, which is
fine, because they were cheap anyway.

Brent's bar (2026-11-22) is "fix it or remove something". If caching doesn't cut the cost enough,
the fallback is to skip blurbs for `Witt/` notes. That would be a separate quick spec.

## Acceptance Criteria
```gherkin
Feature: Cached document prefix for context blurbs

  Scenario: The document is a cached block that comes before the chunk
    Given a note "Spec" with content D and a chunk with text C
    When ContextGenerator generates the blurb
    Then messages.create receives one user message with two text blocks
    And block 1 is '<document title="Spec">\n' + D + '\n</document>' with cache_control {"type": "ephemeral"}
    And block 2 is C wrapped in the chunk tag, followed by the unchanged instruction "Write a 1-2 sentence context blurb for this chunk.", with no cache_control
    And the system prompt and model are unchanged

  Scenario: Every chunk of a note sends a byte-identical prefix
    Given a note with 3 chunks
    When generate_blurbs runs
    Then the system prompt and block 1 are identical across all 3 calls, and only block 2 differs

  Scenario: Cache tokens are priced and logged
    Given a response with input_tokens 100, cache_creation_input_tokens 10000, cache_read_input_tokens 0, output_tokens 20
    And a second response with input_tokens 100, cache_creation_input_tokens 0, cache_read_input_tokens 10000, output_tokens 20
    When both are logged
    Then the first cost is (100 + 10000 × 1.25) × $1/MTok + 20 × $5/MTok, which is approx $0.012700
    And the second cost is (100 + 10000 × 0.1) × $1/MTok + 20 × $5/MTok, which is approx $0.001200
    And each row's input_tokens is the total input (uncached + write + read)
    And its metadata records cache_write_tokens and cache_read_tokens

  Scenario: Responses without cache fields still log correctly
    Given a response whose usage has no cache fields, or non-integer ones (a mock or an older SDK)
    When it is logged
    Then cache write and read count as 0 and the cost equals calculate_cost(input, output) as before

  Scenario: calculate_cost stays backward compatible
    When calculate_cost("anthropic", "claude-haiku-4-5", 1000, 100) is called with no cache arguments
    Then it returns the same value as before this change

  Scenario: An API error still degrades to an empty blurb
    Given messages.create raises anthropic.BadRequestError
    When the blurb is generated
    Then "" is returned, an error row is logged with 0 tokens, and no exception is raised
```

## Files
| File | Action | Note |
|---|---|---|
| `src/secondbrain/indexing/context.py` | Update | two content blocks with `cache_control` on the document; log cache-aware cost, total input tokens and cache metadata |
| `src/secondbrain/stores/usage.py` | Update | `calculate_cost(..., *, cache_write_tokens=0, cache_read_tokens=0)` at 1.25× / 0.1× of the input rate |
| `tests/test_context_generator.py` | Update | the request-shape, identical-prefix, cache-logging and missing-fields scenarios |
| `tests/test_usage_store.py` | Update | the cache pricing and backward-compatibility scenarios |
