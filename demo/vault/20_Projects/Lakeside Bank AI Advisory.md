---
type: project
tags: [client, financial-services, ai-strategy]
status: active
client: Lakeside Bank
created: 2026-03-17
updated: 2026-05-15
---

## Objective

Advise Lakeside Bank's CTO and product leadership on where LLMs and AI will actually move the needle for them in the next 12–18 months — and where it won't. They're under board pressure to "have an AI strategy" but don't want to chase hype.

My job is to help them pick 2–3 real bets and pass on the other 20.

## Key Milestones

- [x] Initial scoping with CTO (David Tran) *(2026-03-24)*
- [x] Landscape brief — what other regional banks are actually shipping *(2026-04-15)*
- [x] Q2 review with David + product leads *(2026-04-30)*
- [ ] Hybrid retrieval working session with their data team *(2026-05-14)*
- [ ] Q3 strategy memo *(due 2026-06-01)*
- [ ] Board presentation prep with David *(2026-06-08)*

## Current Hypotheses (to validate by Q3 memo)

1. **Internal knowledge search** — their compliance/policy docs are a nightmare. RAG over policies for their advisors is a clear, low-risk win.
2. **Loan officer copilot** — assist with summarization of application packets, draft underwriting notes. Medium-risk.
3. **NOT customer-facing chat.** They want to. They shouldn't yet. Regulatory exposure is too high.

## Stakeholders

- **David Tran** — CTO. Smart, skeptical, my main contact. Hates buzzwords.
- **Anika Reddy** — Head of Product. Wants to ship something visible.
- **Compliance / Legal** — represented by Tomás Ruiz. Quiet but powerful.

## Open Questions

- Where does the data live? Their existing data warehouse is fragmented across 3 systems. RAG over policies is doable; loan officer copilot is much harder.
- Build vs. buy on the RAG layer — is there an off-the-shelf option that's HIPAA/SOC2/GLBA-compliant enough?
- How much should the Q3 memo say about Northgate Health-style migrations as a precondition?

## Related
- [[Lakeside Q2 Review]]
- [[Hybrid retrieval]]
- [[RAG fundamentals]]
