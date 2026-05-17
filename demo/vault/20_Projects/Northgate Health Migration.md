---
type: project
tags: [client, healthcare, data-platform]
status: active
client: Northgate Health
created: 2026-04-21
updated: 2026-05-15
---

## Objective

Help Northgate Health migrate their analytics platform from on-prem Snowflake to a cloud-native lakehouse (Databricks). The real work is less about the technology swap and more about:

1. Cleaning up 40+ stale dashboards nobody owns
2. Establishing data ownership and lineage discipline before the migration so it doesn't replicate the mess
3. De-risking PHI handling (HIPAA) — the existing setup has access controls that won't translate cleanly

## Key Milestones

- [x] Engagement kickoff with Priya (CTO) and her data eng team *(2026-05-12)*
- [ ] Discovery doc — current-state architecture + risk register *(due 2026-05-19)*
- [ ] Data lineage walkthrough with DBA team *(scheduled 2026-05-20)*
- [ ] Phase 1 plan + cost model *(due 2026-05-23)*
- [ ] Steering committee presentation *(2026-06-03)*
- [ ] Phase 1 kickoff *(target 2026-06-10)*

## Stakeholders

- **Priya Iyer** — CTO, decision-maker. Engineering background, pragmatic. Doesn't want a 12-month vendor-led migration.
- **Marcus Webb** — Director of Data Eng, reports to Priya. Lived through the current Snowflake setup. Owns lineage.
- **Dr. Lena Park** — Chief Medical Officer. Cares about clinician-facing dashboards. Cannot lose them during migration.
- **Compliance team** — Ben Halloran. HIPAA. Needs a clear data classification matrix before sign-off.

## Open Questions

- 40 stale dashboards: archive in place, or rebuild only the ones owners come forward for? Lean toward the latter — natural cleanup.
- Databricks vs. Snowflake-on-AWS — Priya is leaning Databricks but hasn't committed. Need to decide by Phase 1 plan.
- How aggressive on PHI minimization in the migration? Opportunity to scope down what gets replicated.

## Risk Register

- **High:** Stale dashboards with unknown PHI exposure. Mitigation: inventory before migration starts.
- **High:** Clinician-facing dashboards (~6 critical) cannot have downtime > 4 hours. Mitigation: parallel-run pattern.
- **Medium:** Compliance review may add 4–6 weeks. Mitigation: engage Ben week 1.
- **Medium:** Internal data eng team morale — they're tired. Mitigation: don't position this as "you did it wrong."

## Related
- [[Lakeside Bank AI Advisory]] — similar discovery pattern
- [[Northgate Kickoff Notes]]
