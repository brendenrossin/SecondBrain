# Windsurf Global Workflows & Rules

These are global workflows and rules for use across all projects and repositories, regardless of language (Go, TypeScript, Python, etc.).

**Installation:**
- Rules: `~/.windsurf/rules/` (global) or `.windsurf/rules/` (per-repo)
- Workflows: `~/.windsurf/workflows/` (global) or `.windsurf/workflows/` (per-repo)

Since these are language-agnostic, install them globally.

---

## File 1: `~/.windsurf/rules/engineering-standards.md`

```markdown
# Engineering Standards

## Trigger
Activation: always

## Content

You follow these engineering standards across all projects.

### Code Quality
- **Simple over clever.** Three similar lines of code are better than a premature abstraction. Don't build utilities or helpers for one-time operations.
- **Only build what's asked for.** Don't add features, refactor surrounding code, or make "improvements" beyond what was requested. A bug fix doesn't need the surrounding code cleaned up.
- **Follow existing patterns.** Match the conventions, style, and architecture already established in the codebase. Read before you write.
- **Don't design for hypothetical requirements.** Build for the current need. No feature flags, backwards-compatibility shims, or extensibility hooks unless explicitly requested.
- **Delete cleanly.** If something is unused, remove it completely. No commented-out code, no `_unused` renames, no `// removed` markers.

### Testing
- **Test real behavior, not mocks.** Tests should fail if the underlying business logic breaks. Mock external boundaries (APIs, databases, file systems), not internal logic.
- **Cover the critical path.** Every function with branching, error handling, or business rules needs tests. Skip tests only for trivial wrappers or functions correct by inspection.
- **Tests are documentation.** Test names should describe expected behavior, not implementation details.

### Safety & Reliability
- **All external calls need timeouts.** HTTP clients, database connections, API calls — nothing should be able to hang indefinitely.
- **Validate at system boundaries.** User input, external API responses, file reads — validate and handle errors at the edges. Trust internal code.
- **Never commit secrets.** No API keys, credentials, or tokens in code. Use environment variables and confirm `.env` / secrets files are in `.gitignore`.
- **Avoid silent failures.** Log errors with enough context to debug. Don't swallow exceptions without explanation.

### Architecture
- **Feature specs are the contract.** If a spec exists, implementation is graded against it. Deviations need documented justification.
- **Ship thin vertical slices.** End-to-end working feature over partial infrastructure. A feature that works is better than a framework that doesn't.
- **Minimize blast radius.** Prefer small, focused changes over sweeping refactors. If a change touches more than 5 files, consider breaking it up.
```

---

## File 2: `~/.windsurf/workflows/scope.md`

```markdown
# Scope — Feature Scoping & Architecture Planning

Analyze requirements and produce a feature spec with implementation plan before writing any code. Think like a senior PM and staff-level engineer.

## Steps

### Step 1: Understand the requirement
Read the user's request carefully. Identify:
- What problem are we solving?
- Who is affected and what does success look like?
- What are the constraints (timeline, backward compatibility, performance)?

If the requirement is ambiguous, ask clarifying questions. Do NOT proceed to design until requirements are clear.

### Step 2: Explore the codebase
Search for related files, existing patterns, and potential conflicts:
- Find the files that will need to change
- Identify existing abstractions and conventions to build on
- Check for architecture docs, READMEs, or existing feature specs
- Look at recent git history for the affected area

Understand what exists before proposing what to build.

### Step 3: Evaluate approaches
Consider at least 2 approaches when the solution isn't obvious. For each:
- What files change and how many?
- What are the trade-offs (complexity, performance, maintainability)?
- Does it follow or break existing patterns?

Recommend one approach with clear rationale.

### Step 4: Write the feature spec
Create a spec document (in the project's docs directory or as specified by the user) with:

**Header:**
- Feature name and short description
- Status (Planned)
- Estimated effort
- Dependencies

**Body:**
- **Problem** — What friction or gap exists today
- **Solution** — High-level approach and recommended option
- **Work Items** — Each discrete unit of work with: goal, behavior, files to modify
- **Implementation Order** — Which work items depend on which
- **What's Explicitly Out of Scope** — Things we're deliberately NOT building (with rationale)
- **Testing** — What automated tests are needed, what manual QA to perform
- **Design Decisions** — Key choices made and why (this is the most valuable section for future reference)

### Step 5: Risk assessment
Identify and flag:
- Breaking changes to existing functionality
- Security implications (auth, input validation, data exposure)
- Performance impact (new queries, API calls, compute)
- Data migration or state changes
- Anything that requires extra review or rollback planning

### Step 6: Create implementation prompt
Write a clear, self-contained prompt that an implementation agent (or another session) can follow to build the feature:
- Reference the feature spec path
- List specific files to modify with what changes
- Specify implementation order
- Define testing requirements
- State what's out of scope so it doesn't over-build
- Include the commit workflow the project uses

### Step 7: Present for approval
Summarize the spec to the user in a concise format:
- 2-3 sentence summary of what will be built
- Number of work items and estimated file changes
- Key trade-offs or decisions that need sign-off
- Any risks flagged

Do NOT begin implementation until the user approves the approach.
```

---

## File 3: `~/.windsurf/workflows/review.md`

```markdown
# Review — Technical Implementation Review

Review the implementation against the feature spec. Grade for correctness, spec compliance, test coverage, and code quality. Think like a staff engineer doing a thorough code review.

## Steps

### Step 1: Load the spec
Find and read the relevant feature spec or requirements doc. This is the contract — the implementation is graded against it. If no spec exists, use the original user request and conversation context as the baseline.

### Step 2: Inventory all changes
Run `git diff --stat HEAD` and `git diff HEAD` to see every changed file. Also check `git status` for any untracked files. Read each modified and new file in full. Do NOT skip any files — surprises live in the files you didn't read.

### Step 3: Verify spec compliance
For each work item or requirement in the spec:
- Was it implemented? (Yes / Partial / No / Deviated)
- If deviated, is there documented justification?
- Were any unrequested changes made? (scope creep)

Create a checklist tracking every requirement.

### Step 4: Code quality review
For each changed file, check:
- Does it follow existing codebase patterns and conventions?
- Are there any obvious bugs, edge cases, or error handling gaps?
- Is there unnecessary complexity, premature abstraction, or dead code?
- Are external calls (APIs, DB, network) properly protected with timeouts and error handling?
- Are there any security concerns (injection, unvalidated input, exposed secrets)?

### Step 5: Test coverage review
- Do new/modified functions with business logic, branching, or error handling have tests?
- Are tests testing real behavior or just mocking everything? (Tests should fail if the underlying code breaks)
- Run the full test suite and confirm all tests pass
- Run the project's lint and format checks
- Flag any untested critical paths

### Step 6: Grade and report
Grade each component (Backend, API, Frontend, Tests, Infrastructure — whichever apply) on an A-F scale.

Classify every issue found:
- **Critical** — Must fix before commit (data loss, security vulnerability, spec violation, broken functionality)
- **Medium** — Should fix before commit (missing validation, incorrect edge case behavior, missing tests for critical path)
- **Low** — Document for later (style nits, minor optimizations, nice-to-haves)

### Step 7: Deliver verdict
If Critical or Medium issues exist:
- List each issue with file path, line number, and what needs to change
- Do NOT commit. Report findings for the implementer to fix.

If all issues are Low or none:
- State "Ready to commit" with a summary of what was built
- List any Low issues to document for future cleanup
- Suggest a commit message based on the changes

Format the report as a clear table or checklist the user can act on.
```

---

## File 4: Update your existing commit workflow

Add `/review` as the first step in your existing pre-commit sweep. Example integration:

```markdown
# Commit — Pre-Commit Sweep

Full quality sweep before committing code changes.

## Steps

### Step 1: Technical review
Call /review

If the review surfaces Critical or Medium issues, stop here. Fix the issues before continuing.

### Step 2: Test generation
[your existing test-generation step]

### Step 3: Code simplification
[your existing code-simplifier step]

### Step 4: Feature documentation
If a major feature was completed, generate a devlog entry documenting what was built, key decisions, and patterns established.

### Step 5: Commit
Stage relevant files (not secrets or generated artifacts). Generate a descriptive commit message summarizing the "why" not the "what". Commit.
```

---

## How These Work Together

```
Feature request
    │
    ▼
 /scope  ──────►  Feature spec written  ──►  User approves
                                                   │
                                              Implementation
                                              (by agent or you)
                                                   │
                                                   ▼
 /commit  ──►  /review (grading)  ──►  Fix issues if any
                    │
                    ▼
              Test generation  ──►  Code simplification  ──►  Commit + Push
```

**`/scope`** ensures you think before you build.
**`/review`** (inside `/commit`) ensures what was built matches what was planned.
**Engineering standards rule** (always on) keeps the AI aligned during implementation itself.

---

## Notes

- These are deliberately **language-agnostic**. They say "run the project's lint/format checks" not "run ruff" or "run eslint". The AI reads the project's Makefile/package.json/taskfile to figure out the right commands.
- **No project-specific paths or tools** are referenced. Each project's own rules file (`.windsurf/rules/`) or README can layer on project-specific conventions.
- The `/scope` workflow produces an **implementation prompt** that can be handed to a separate agent session — this is key for keeping the PM/architect role separate from the implementer.
- The `/review` workflow explicitly checks **spec compliance first**, then code quality. This ordering matters — it catches missed requirements before bikeshedding code style.
