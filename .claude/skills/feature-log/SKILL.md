---
name: feature-log
description: Log a completed major feature or epic to the project devlog. Use this proactively after completing a significant feature, epic, or architectural change — not for small tweaks, lint fixes, or minor adjustments.
argument-hint: "[feature name]"
---

# Feature Log

Create or update feature documentation for the project devlog. This captures institutional knowledge so future development (by humans or AI) can build on what was learned.

## When to use this

- After completing a **major feature** or **epic** (not small tweaks)
- After significant **architectural changes**
- After completing a **multi-file refactor** with meaningful design decisions

## Instructions

1. Determine the feature name from `$ARGUMENTS` or from the current conversation context
2. Generate a date stamp in `YYYY-MM-DD` format
3. Create a markdown file at `docs/devlog/features/{YYYY-MM-DD}-{feature-name-slug}.md`
4. If a file for this feature already exists (same slug, different date), update it instead of creating a duplicate
5. Fill in the template below based on the current conversation and git history

## Template

```markdown
# Feature: {Feature Name}

**Date:** {YYYY-MM-DD}
**Branch:** {git branch name if applicable}

## Summary

{2-3 sentence description of what was built and why}

## Problem / Motivation

{What problem does this solve? Why was it needed?}

## Solution

{High-level description of the approach taken}

## Files Modified

{List of files created or modified, grouped logically}

## Key Decisions & Trade-offs

{Decisions made during implementation and why — this is the most valuable section for future reference}

## Patterns Established

{Any new patterns, conventions, or architectural precedents set by this feature that future work should follow}

## Testing

{How was this tested? What should be verified?}

## Future Considerations

{Known limitations, things that might need revisiting, or follow-up work}
```

## After writing

- Confirm the file was written with the user
- Do NOT commit automatically — let the user decide when to commit
