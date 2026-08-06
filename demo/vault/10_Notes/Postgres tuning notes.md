---
type: note
tags: [research, infrastructure, database]
created: 2026-04-04
updated: 2026-05-03
---

## Summary

Notes from a deep dive on Postgres tuning while Pantry was hitting query latency on the recipe library. Most of it ended up not mattering — the real fix was an index.

## What actually mattered

- **Missing index on the user_recipes join.** Adding it dropped p99 from 600ms to 12ms. As usual, the boring answer wins.
- **`work_mem`** at default (4MB) was causing on-disk sorts for some analytics queries. Bumped to 64MB for the analytics user, kept default for app users.
- **`effective_cache_size`** — I had it at default. Setting to ~75% of RAM helped the planner pick better paths.

## What didn't matter (for me)

- Connection pool tuning beyond defaults. PgBouncer made things *slower* at my scale.
- Partitioning. Way too early.
- Switching to a different storage engine. Postgres is fine.

## Rules of thumb I'm now collecting

- "Slow query" → check EXPLAIN, look for sequential scans on big tables, add the index.
- `pg_stat_statements` is the single best tool for finding the queries that actually matter.
- Don't tune anything before you've measured.

## Related
- [[Async Python patterns]]
- [[Pantry]]
