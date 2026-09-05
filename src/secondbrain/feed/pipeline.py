"""Feed pipeline: config -> fetch -> dedup -> rank -> persist -> summarize -> prune.

Filter-before-you-spend: every step up to `summarize_items` is free. Only the
top-N survivors reach the single batched LLM call.
"""

import logging
from pathlib import Path

from secondbrain.config import Settings
from secondbrain.feed.config import load_feed_config
from secondbrain.feed.fetch import fetch_all
from secondbrain.feed.models import FeedItem, FeedSummary
from secondbrain.feed.rank import dedup_items, rank_items, select_top_n
from secondbrain.feed.summarize import summarize_items
from secondbrain.stores.feed import FeedStore
from secondbrain.stores.usage import UsageStore

logger = logging.getLogger(__name__)


def _attach_takes(top: list[FeedItem], summary: FeedSummary) -> None:
    """Copy each section's per-item take back onto the matching item, keyed by URL."""
    takes = {i["url"]: i.get("take") for s in summary.sections for i in s.items}
    for item in top:
        take = takes.get(item.url)
        if take:
            item.summary = take


def run_feed_pipeline(vault_path: Path, settings: Settings) -> str:
    """Run the full feed refresh. Returns a one-line summary for logs."""
    if not settings.feed_enabled:
        return "Feed disabled (feed_enabled=False)"

    config = load_feed_config(vault_path, settings.feed_config_path)
    raw = fetch_all(config.sources)
    unique = dedup_items(raw)
    ranked = rank_items(unique, config.interests)

    data_path = Path(settings.data_path)
    store = FeedStore(data_path / settings.feed_db_name)
    try:
        store.add_items(ranked)  # persist the full ranked list — rows are cheap
        top = select_top_n(ranked, settings.feed_top_n, settings.feed_min_per_type)

        usage_store = UsageStore(data_path / "usage.db")
        try:
            summary = summarize_items(top, settings, usage_store)
        finally:
            usage_store.close()

        _attach_takes(top, summary)
        store.update_summaries(top)
        store.mark_shown([it.url for it in top])
        pruned = store.prune_old(settings.feed_retention_days)
    finally:
        store.close()

    return (
        f"Feed: {len(raw)} fetched, {len(unique)} unique, {len(top)} summarized "
        f"(generated={summary.generated}), {pruned} pruned"
    )
