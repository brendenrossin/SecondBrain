# Feed Configuration (FEED-1)

The attention router reads its sources and interest weights from a note **in your
vault** — the vault stays the source of truth. Copy the block below into
`_config/feed.md` (path configurable via `SECONDBRAIN_FEED_CONFIG_PATH`) and edit
freely; the file is read fresh on every refresh.

If the note is absent, unreadable, or malformed, the pipeline falls back to the
seed defaults in `src/secondbrain/feed/config.py` and logs a warning. It never crashes.

## Example `_config/feed.md`

```markdown
---
sources:
  # --- AI ---
  - url: https://simonwillison.net/atom/everything/
    label: Simon Willison
    type: ai
    trust: 0.9
  - url: https://www.latent.space/feed
    label: Latent Space
    type: ai
    trust: 0.8
  - url: https://importai.substack.com/feed
    label: Import AI
    type: ai
    trust: 0.8
  - url: https://www.technologyreview.com/topic/artificial-intelligence/feed
    label: MIT Tech Review AI
    type: ai
    trust: 0.7
  - url: https://hnrss.org/newest?q=AI&points=100
    label: Hacker News AI
    type: ai
    trust: 0.6
  # --- Sports ---
  - url: https://www.mlb.com/padres/feeds/news/rss.xml
    label: Padres
    type: sports
    trust: 0.8
  - url: https://mgoblog.com/rss.xml
    label: Michigan FB (MGoBlog)
    type: sports
    trust: 0.7
  - url: https://www.espn.com/espn/rss/nfl/news
    label: NFL (ESPN)
    type: sports
    trust: 0.6

interests:
  agents: 2.0
  anthropic: 2.0
  claude: 1.8
  llm: 1.5
  rag: 1.5
  eval: 1.2
  openai: 1.2
  model: 1.0
  prompt: 1.0
  padres: 2.0
  michigan: 2.0
  wolverines: 1.8
  nfl: 1.2
  playoff: 1.2
---

# Feed Config

Notes to self about why these sources are here.
```

### Fields

| Field | Meaning |
|---|---|
| `url` | RSS/Atom feed URL. Required — an entry without one is skipped. |
| `label` | Display name in the UI. Defaults to the URL. |
| `type` | `ai`, `sports`, or `general`. Drives section grouping and the per-type minimum. |
| `trust` | `0.0`–`1.0` source-quality multiplier in the ranking score. Defaults to `0.5`. |
| `interests` | keyword → weight. Matched case-insensitively against title + snippet. |

Scoring is `trust × (1 + Σ matched interest weights) × recency_decay`, where recency
decays exponentially with a 48-hour half-life. It's pure heuristics — no LLM, no
embeddings — which is what keeps the filtering free.

## Enabling

```bash
# .env
SECONDBRAIN_FEED_ENABLED=true
```

Other knobs (all optional, defaults in `src/secondbrain/config.py`):

| Setting | Default | Meaning |
|---|---|---|
| `SECONDBRAIN_FEED_CONFIG_PATH` | `_config/feed.md` | Vault-relative config note |
| `SECONDBRAIN_FEED_TOP_N` | `10` | Items sent to the one summary call |
| `SECONDBRAIN_FEED_MIN_PER_TYPE` | `3` | Guaranteed slots per type, so one domain can't crowd out the other |
| `SECONDBRAIN_FEED_SUMMARY_MODEL` | `claude-haiku-4-5` | Model for the batched summary |
| `SECONDBRAIN_FEED_RETENTION_DAYS` | `30` | Age at which feed rows are pruned |

## Scheduling

No new launchd job is needed. The existing `com.secondbrain.daily-sync.plist` runs
`daily_sync all`, which now includes a `feed` step. That step runs **last** and
catches its own exceptions: the feed is discretionary and depends on the network
plus an LLM, so a failure must never abort inbox/tasks/projects/index/extract.

Because the sync runs well before the 9:15 AM iOS digest pull, the feed is already
refreshed by the time the digest fires, and its counts appear in the push body
("5 AI updates · 3 sports").

Refresh on demand:

```bash
uv run python -m secondbrain.scripts.daily_sync feed --vault-path "$SECONDBRAIN_VAULT_PATH" -v
```

## Cost

One batched `claude-haiku-4-5` call per refresh over the top-N items — roughly
$0.15/month at daily cadence. Everything before that call (fetch, dedup, recency
decay, interest scoring, top-N selection) is free. Every failure path falls back to
headlines, so a missing API key or a model error costs nothing and still renders.

Each call is logged to `UsageStore` with `usage_type="feed_summary"`; the Admin
dashboard shows the per-type cost breakdown.
