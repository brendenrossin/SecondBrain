---
type: project
tags: [side-project, mobile, ai]
status: active
created: 2026-02-14
updated: 2026-05-16
---

## Objective

Build "Pantry" — a recipe app that suggests meals based on what's currently in your fridge. Camera scan or manual entry, LLM-assisted matching against a recipe library, ranked by ingredient overlap and personal taste signal.

The bet: most recipe apps assume you're shopping *for* a recipe. Pantry inverts that — you have ingredients, what should you cook tonight?

## Key Milestones

- [x] v0.1 — manual fridge entry, hand-curated 100-recipe library *(shipped 2026-03-04)*
- [x] v0.2 — camera scan via [[Vision OCR pipeline]] *(shipped 2026-03-28)*
- [x] v0.3 — LLM-based meal suggestions using fridge + dietary preferences *(shipped 2026-04-22)*
- [ ] v0.4 — protein-weighting, "save recipe variant" UX, TestFlight push *(target 2026-05-19)*
- [ ] v0.5 — shopping list mode (what to buy for the *gap* between fridge and recipe)
- [ ] v0.6 — multi-meal planning across a week
- [ ] v1.0 — public App Store launch

## Open Questions

- How do we surface "you've cooked this 3 times this month" without feeling creepy?
- Is voice input worth it for fridge entry? Marcus said yes, Sam said no.
- Recipe library: hand-curated forever, or open user submissions at some point?

## Recent feedback

- Marcus (user test, 2026-05-12): "Feels too vegetarian." → protein-weighting in v0.4.
- Sam: wants ingredient substitutions surfaced inline (e.g. "no buttermilk → use yogurt + lemon").
- Me (2026-05-16): tried [[Honey Miso Salmon]], tweaked the sauce — Pantry should let users save variants of a recipe.

## Related
- [[RAG fundamentals]] — how meal suggestions retrieve recipes
- [[LLM cost optimization]] — keeping inference costs under $0.01/suggestion
- [[Hybrid retrieval]] — BM25 on ingredient names + vector on flavor profile
