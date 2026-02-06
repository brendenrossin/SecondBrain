---
name: error-log
description: Log a significant error, bug, or corruption issue that was diagnosed and fixed. Use this proactively after resolving non-trivial bugs, data corruption, infrastructure issues, or persistent errors that required real debugging — not for simple lint fixes or typos.
argument-hint: "[error name]"
---

# Error Log

Document a significant error or bug that was found and fixed. This builds institutional knowledge to prevent repeating the same mistakes and helps diagnose similar issues faster in the future.

## When to use this

- After fixing a **non-trivial bug** that required real debugging
- After resolving **data corruption** or **infrastructure issues**
- After diagnosing a **persistent or recurring error**
- After fixing issues caused by **incorrect assumptions** about how something works
- NOT for simple lint errors, typos, or trivial fixes during development

## Instructions

1. Determine the error name from `$ARGUMENTS` or from the current conversation context
2. Generate a date stamp in `YYYY-MM-DD` format
3. Create a markdown file at `docs/devlog/errors/{YYYY-MM-DD}-{error-name-slug}.md`
4. Fill in the template below based on the current conversation, git history, and debugging context

## Template

```markdown
# Error: {Error Name}

**Date:** {YYYY-MM-DD}
**Severity:** {Critical / High / Medium}
**Component:** {Which part of the system was affected}

## Symptoms

{What was observed? Error messages, unexpected behavior, data issues}

## Root Cause

{The actual underlying cause — this is the most important section. Be specific.}

## Fix Applied

{What was changed to fix it, and why this approach was chosen}

## Files Modified

{List of files changed as part of the fix}

## How to Prevent

{What practices, checks, or architectural decisions would prevent this class of error in the future}

## Lessons Learned

{Key takeaways — incorrect assumptions that were corrected, things that should have been done differently from the start}

## Detection

{How was this error discovered? How could it be detected earlier next time?}
```

## After writing

- Confirm the file was written with the user
- Do NOT commit automatically — let the user decide when to commit
