---
name: tri-review
description: Tri-persona post-implementation review. Run after completing a feature, bugfix, or significant code change. Three specialized reviewers (Security Sentinel, Optimization Architect, Quality Auditor) independently evaluate the code, then a Meta-Judge synthesizes findings by agreement level. Produces a prioritized report and auto-applies approved fixes.
argument-hint: "[branch name, file paths, or feature description]"
---

# Tri-Persona Code Review

Perform a multi-pass evaluation of recently built code by simulating three specialized AI personas. Each pass reviews independently, then findings are consolidated through an agreement matrix to surface only high-signal issues.

## When to Use

- After completing a feature, epic, or significant bugfix
- Before creating a PR or merging to main
- After a major refactor or architectural change
- When code touches security-sensitive paths (auth, user input, external APIs)

## Pass 1: The Security Sentinel

Focus: Security risks, resilience, and operational safety.

Review the changed code for:

- **Injection risks** -- SQL injection, command injection, XSS, path traversal
- **Data leaks** -- exception messages exposing internals, verbose error responses, logging sensitive data
- **Authentication/authorization gaps** -- missing auth checks, privilege escalation paths
- **Race conditions** -- concurrent access to shared state, TOCTOU vulnerabilities
- **Timeout and retry safety** -- missing timeouts on external calls, retry storms, exponential backoff gaps
- **Error handling** -- bare exceptions swallowing errors, missing cleanup in error paths, partial state corruption
- **Secret management** -- hard-coded credentials, API keys in code, secrets in logs
- **Dependency risks** -- known-vulnerable packages, unnecessary permissions

Output a numbered list of findings with file path, line number, severity (Critical/High/Medium/Low), and a concrete fix suggestion.

## Pass 2: The Optimization Architect

Focus: Performance, efficiency, scalability, and architectural soundness.

Review the changed code for:

- **Performance** -- unnecessary allocations, N+1 queries, blocking I/O in async paths, missing caching opportunities
- **Resource management** -- unclosed connections/files, memory leaks, unbounded collections
- **Scalability** -- patterns that break under load, missing pagination, unbounded result sets
- **Architecture** -- violations of existing patterns, unnecessary coupling, abstraction mismatches
- **Async correctness** -- blocking calls in async context, untracked tasks, missing `await`
- **Configuration** -- magic numbers, missing environment variable validation, hard-coded URLs/ports

Output a numbered list of findings with file path, line number, severity, and a concrete fix suggestion.

## Pass 3: The Quality Auditor

Focus: Correctness, test quality, code clarity, and API design.

Review the changed code for:

- **Correctness** -- logic errors, off-by-one, wrong operator, missing edge cases
- **Test quality** -- do tests validate real behavior and critical paths, not just mocks? Are failure scenarios covered?
- **Input validation** -- is user input strictly validated at system boundaries?
- **Dead code** -- has unused code been deleted cleanly (no commented-out blocks)?
- **API design** -- is the API/component easy to use correctly and hard to misuse?
- **Error messages** -- are they actionable for the user/developer?
- **Type safety** -- missing type annotations on public interfaces, `Any` types hiding bugs

Output a numbered list of findings with file path, line number, severity, and a concrete fix suggestion.

## Synthesis & Triage (The Meta-Judge)

Consolidate findings from all three passes into a single source of truth.

1. **Deduplicate** -- Merge identical or overlapping findings across passes.
2. **Filter** -- Reject unsupported claims (findings without concrete code evidence) and ignore subjective stylistic nitpicks.
3. **Apply Agreement Matrix:**
   - **3 personas agree:** High Confidence -- Fix immediately.
   - **2 personas agree:** Medium Confidence -- Investigate closely.
   - **1 persona flags:** Low Confidence -- Worth reading; may catch subtle edge cases.
4. **Prioritize** -- Rank the final backlog by severity (Critical, High, Medium, Low, Nit) and impact vs. effort.

## Execution & Output

### 1. Report to Chat

Output the **Optimization Report** directly in the chat with:
- Prioritized findings table (severity, agreement level, file:line, description, fix)
- Summary stats (total findings, by severity, by pass)

Do NOT save this report as a file to prevent committing sensitive evaluation data.

### 2. Optimization Backlog

Append deferred items (Medium confidence or lower, Low/Nit severity) to an **Optimization Backlog** at:
```
docs/optimizations/[feature-or-epic-name]-backlog.md
```
Infer the feature/epic name from the branch name, commit messages, or user request. Create the directory and file if they do not exist.

### 3. Apply Fixes

- Present Critical/High confidence findings to the user and ask which to auto-apply.
- Implement the smallest safe change for each approved item.
- Run `make check` to verify fixes don't introduce regressions.
- Stop when no Critical/High findings remain or diminishing returns are reached.
