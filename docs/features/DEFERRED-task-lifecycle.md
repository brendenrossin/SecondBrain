# Task Lifecycle Engine (Deferred)

> **Status:** Deferred indefinitely
> **Original proposal:** Phase 3.6 in brainstorm roadmap
> **Decision date:** 2026-02-07

## What Was Proposed

A full task state machine with:
- States: todo | doing | blocked | waiting | done
- State transitions + audit log
- "Stuck task" heuristics
- Quick state change controls in UI
- JSON export/import

## Why Deferred

### Source-of-truth conflict
Tasks currently live in the Obsidian vault (daily notes). The task aggregator reads them, deduplicates, and serves them via API. Adding states in a database creates a second source of truth. The existing bi-directional sync between aggregate files and daily notes is already the most fragile part of the system — adding more state to sync would compound that fragility.

### Disproportionate maintenance cost
A state machine with audit logging, state transitions, and UI controls is a PM tool. Building and maintaining it is significant effort for a single-user system where the current binary (open/completed) model works.

### Current heuristics cover the need
- `days_open` already identifies long-running tasks
- `due_date` already surfaces urgency
- Category/sub-project already provides organization
- The frontend already renders all of this

## What We're Doing Instead

- Task visibility via the existing aggregator + Next.js frontend
- Due date tracking (already implemented)
- Days open tracking (already implemented)
- Category/sub-project grouping (already implemented)

## Conditions to Revisit

- If the binary open/completed model proves insufficient after 3+ months of daily use
- If the user consistently needs states beyond open/completed (doing, blocked, waiting)
- If a clean way to store state in the vault itself (e.g., frontmatter or task metadata syntax) emerges that avoids the second-source-of-truth problem
