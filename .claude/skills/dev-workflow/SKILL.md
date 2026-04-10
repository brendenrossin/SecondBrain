---
name: dev-workflow
description: Full development lifecycle for implementing a roadmap ticket. Use when starting work on any ticket — orchestrates the entire flow from pickup through brainstorming, planning, implementation, review, PR, and delivery. This is the master workflow that invokes other skills in sequence.
argument-hint: "[ticket ID, e.g. TRACE-1]"
---

# Development Workflow

The end-to-end lifecycle for implementing a roadmap ticket. This skill orchestrates other skills in the correct sequence, enforcing quality gates at each stage.

## When to Use

- Starting work on any roadmap ticket
- User says "let's work on TRACE-1" or "pick up the next ticket"
- Beginning a new feature, bugfix, or epic item

## The Workflow

```
1. Roadmap Start  ──►  2. Brainstorm  ──►  3. Plan  ──►  4. Implement
                                                              │
    7. Deliver  ◄──  6. Create PR  ◄──  5. Review  ◄─────────┘
                                            │
                                            └──► (findings?) ──► back to 4
```

### Step 1: Pick Up — `/roadmap start {TICKET}`

- Mark the ticket as **In Progress** on the roadmap
- Read the ticket's spec (if one exists)
- Report what we're building and any dependencies

### Step 2: Brainstorm — `/brainstorming`

- Validate the existing spec against the current codebase (specs may be stale)
- Clarify requirements, identify unknowns, propose approaches
- Get user approval on the design
- Write/update the design doc

**Gate:** User approves the design before proceeding.

### Step 3: Plan — `/writing-plans`

- Create a detailed implementation plan from the approved design
- Break into discrete, ordered steps
- Identify files to create/modify, dependencies between steps

**Gate:** User approves the plan before proceeding.

### Step 4: Implement

- Execute the plan step by step
- Run `/test-generation` for each substantive function written or modified
- Run `make check` after each logical chunk of work
- Commit incrementally (with `code-simplifier` before each commit per project convention)

**Gate:** All tests pass, `make check` clean.

### Step 5: Review — `/roadmap review {TICKET}`

- Update ticket status to **Review**
- Run `/tri-review` on all changed code
- If Critical/High findings: fix them, re-run tri-review
- Continue until no Critical/High findings remain

**Gate:** Tri-review passes with no Critical/High findings.

### Step 6: Create PR

- Update ticket status to **PR**
- Push branch and create PR via `gh pr create`
- Wait for CI to pass

**Gate:** CI green, PR created.

### Step 7: Deliver — `/roadmap deliver {TICKET}`

- Verify PR is merged (user merges, or merge if user approves)
- Move ticket from `ROADMAP.md` to `DELIVERED.md` with date and PR link
- Run `/feature-log` if the ticket is a major feature or epic

**Gate:** PR merged, ticket archived.

## Handling Interruptions

- **Spec is stale:** Update the spec during brainstorming, commit the update.
- **Tri-review bounces back:** Return to Step 4, fix findings, re-enter Step 5.
- **User wants to change scope mid-flight:** Return to Step 2 (brainstorm), re-plan.
- **Blocked by dependency:** Pause ticket, note the blocker on the roadmap, pick up another ticket.

## Session Boundaries

This workflow often spans multiple sessions. When ending a session mid-workflow:

1. Note which step you're on and what's left
2. Provide a handoff prompt the user can paste into the next session
3. The next session should resume from the current step, not restart from Step 1

## Rules

- **Never skip brainstorming.** Even if a spec exists, validate it.
- **Never skip tri-review.** Every ticket gets reviewed before PR.
- **Never merge without CI green.** Wait for checks to pass.
- **One ticket at a time** unless explicitly parallelizing independent work.
- **Commit early, commit often.** Don't accumulate a massive uncommitted diff.
