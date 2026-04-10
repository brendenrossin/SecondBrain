---
name: roadmap
description: Manage the project roadmap lifecycle. Use when starting work on a ticket (update status to In Progress), adding new tickets to an epic, or completing work (gate on tri-review + PR before moving to DELIVERED.md). Enforces the workflow: pick up → implement → tri-review → PR → merge → deliver.
argument-hint: "[ticket ID or 'add' or 'deliver']"
---

# Roadmap Workflow

Manage the SecondBrain roadmap through its full lifecycle. This skill enforces a disciplined flow from picking up work to delivering it.

## Files

- **`docs/ROADMAP.md`** — Active work. Epics with tickets in various statuses.
- **`docs/DELIVERED.md`** — Shipped work archive. Tickets move here after PR merge.

## Ticket Lifecycle

```
Backlog → Pending → In Progress → Review → PR → [merged] → DELIVERED.md
```

## Commands

### Pick Up Work: `/roadmap start TRACE-1`

1. Read `docs/ROADMAP.md` and find the ticket
2. Verify no unresolved blockers in the dependency tree
3. Update the ticket's status to **In Progress**
4. Report what the ticket is and link to its spec (if any)

### Add a Ticket: `/roadmap add`

1. Ask which epic the ticket belongs to (or create a new epic)
2. Ask for: ticket title, estimate, dependencies, spec link (optional)
3. Assign the next ID in that epic's sequence (e.g., TRACE-4)
4. Add the ticket to `docs/ROADMAP.md` with status **Backlog** or **Pending**

### Complete Implementation: `/roadmap review TRACE-1`

1. Update the ticket's status to **Review**
2. Invoke the `/tri-review` skill on the changed code
3. If tri-review surfaces Critical/High findings, stay in **Review** until resolved
4. Once tri-review passes, update status to **PR**
5. Prompt the user to create a PR (or offer to create one)

### Deliver: `/roadmap deliver TRACE-1`

1. Verify the ticket's PR has been merged (check via `gh pr list --state merged` or user confirmation)
2. Remove the ticket row from `docs/ROADMAP.md`
3. Add the ticket to `docs/DELIVERED.md` with completion date and PR link
4. If this was the last ticket in an epic, move the epic header to `DELIVERED.md` too
5. Commit both file changes

### View Status: `/roadmap status`

1. Read `docs/ROADMAP.md`
2. Show a summary: how many tickets per status, what's in progress, what's blocked

## Epic and Ticket Format

### Epic Header
```markdown
## Epic: Name Here
> One-line description of the epic's goal

| ID | Ticket | Est. | Status | Spec |
|----|--------|------|--------|------|
| PREFIX-N | Ticket description | Xd | **Status** | [spec](path) |
```

### Delivered Entry
```markdown
| PREFIX-N | Ticket description | YYYY-MM-DD | [#N](pr-url) |
```

## ID Conventions

Each epic has a short prefix. Current prefixes:

- `TRACE` — LLM Tracing & Evaluation
- `RAG` — RAG Quality & Performance
- `OPS` — Operations & Infrastructure
- `RETRIEVAL` — Smarter Retrieval & Discovery
- `EMAIL` — Email Ingestion
- `VOICE` — Voice Chat
- `KG` — Knowledge Graph
- `WRITEBACK` — Write-Back Workflow

When creating a new epic, choose a short, descriptive prefix (3-8 chars).

## Integration with Other Skills

This skill gates completion on `/tri-review`. The expected workflow when implementing a ticket:

1. `/roadmap start TRACE-1` — marks In Progress
2. Write code, run `/test-generation`
3. `/roadmap review TRACE-1` — triggers `/tri-review`, then PR creation
4. Merge the PR
5. `/roadmap deliver TRACE-1` — archives to DELIVERED.md

## Rules

- **Never skip tri-review.** Every ticket goes through `/tri-review` before PR.
- **Never move to DELIVERED without a merged PR.** The PR is the proof of delivery.
- **Keep dependency tree updated.** When adding tickets, check if they depend on or unblock others.
- **One ticket = one deliverable.** If a ticket is too big, split it.
