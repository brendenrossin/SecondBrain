"""Feed pipeline: config -> fetch -> dedup -> rank -> persist -> summarize -> prune.

Filter-before-you-spend: every step up to `summarize_items` is free. Only the
top-N survivors reach the single batched LLM call.
"""

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
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


def _is_due(last_fetched_at: str, min_interval_hours: int) -> bool:
    """True when the last refresh is older than the minimum interval.

    An unparseable timestamp counts as due — better one extra refresh than a
    feed that silently stops updating forever.
    """
    try:
        last = datetime.fromisoformat(last_fetched_at)
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return datetime.now(UTC) - last >= timedelta(hours=min_interval_hours)


def _section_overviews(top: list[FeedItem], summary: FeedSummary) -> dict[str, str]:
    """Map each section overview onto the item type it actually describes.

    A section's heading is model-authored free text ("Sports", "AI news", "AI/ML"),
    while the read path groups by our own `type` column. Joining on the types of
    the section's resolved items avoids depending on the model spelling a heading
    the same way twice.

    Only type-pure sections are trusted. A section spanning types means the model
    ignored the grouping instruction, and filing it under the majority type would
    print a sports paragraph under the AI header — confidently wrong reads worse
    than absent. Where the model splits one type across sections ("AI Research",
    "AI Industry"), the overview covering the most items wins rather than
    whichever happened to come last.
    """
    types = {it.url: it.type for it in top}
    best: dict[str, tuple[int, str]] = {}
    for section in summary.sections:
        if not section.overview:
            continue
        counts = Counter(types[i["url"]] for i in section.items if i["url"] in types)
        if len(counts) != 1:
            if counts:
                logger.info("Feed: skipping overview for mixed-type section %r", section.heading)
            continue
        item_type, matched = next(iter(counts.items()))  # exactly one, per the check above
        incumbent = best.get(item_type)
        if incumbent is None or matched > incumbent[0]:
            best[item_type] = (matched, section.overview)
    return {item_type: text for item_type, (_, text) in best.items()}


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

    data_path = Path(settings.data_path)
    store = FeedStore(data_path / settings.feed_db_name)
    try:
        last = store.last_fetched_at()
    except Exception:
        logger.warning("Could not read last feed refresh; proceeding", exc_info=True)
        last = None
    finally:
        store.close()

    # The deployed daily-sync job runs hourly, and `all` includes this step. One
    # LLM call per *run* would therefore be 24 calls a day (~24x the budgeted
    # cost) re-summarizing the same articles. Refresh at most once per window.
    if last is not None and not _is_due(last, settings.feed_min_interval_hours):
        return f"Feed skipped (refreshed {last[:16]}, min interval {settings.feed_min_interval_hours}h)"

    config = load_feed_config(vault_path, settings.feed_config_path)
    raw = fetch_all(config.sources)
    unique = dedup_items(raw)
    ranked = rank_items(unique, config.interests)

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
        store.replace_section_overviews(_section_overviews(top, summary))
        store.mark_shown([it.url for it in top])
        pruned = store.prune_old(settings.feed_retention_days)
    finally:
        store.close()

    return (
        f"Feed: {len(raw)} fetched, {len(unique)} unique, {len(top)} summarized "
        f"(generated={summary.generated}), {pruned} pruned"
    )
