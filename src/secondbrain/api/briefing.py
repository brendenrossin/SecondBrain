"""Morning briefing API endpoint."""

import asyncio
import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from secondbrain.api.dependencies import get_settings
from secondbrain.config import Settings
from secondbrain.models import (
    BriefingResponse,
    BriefingTask,
    DailyContext,
    DigestResponse,
    EventResponse,
)
from secondbrain.scripts.event_parser import get_events_in_range
from secondbrain.scripts.task_aggregator import (
    AggregatedTask,
    aggregate_tasks,
    find_recent_daily_context,
    parse_daily_note_sections,
    scan_daily_notes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["briefing"])

# Simple TTL cache matching tasks.py pattern
_cache: dict[str, object] = {"data": None, "ts": 0.0}
_CACHE_TTL = 60.0


def _to_briefing_task(t: AggregatedTask) -> BriefingTask:
    """Convert an AggregatedTask to a BriefingTask."""
    return BriefingTask(
        text=t.text,
        category=t.category,
        sub_project=t.sub_project,
        due_date=t.due_date,
        days_open=t.days_open,
        first_date=t.first_date,
    )


def _feed_counts(settings: Settings) -> dict[str, int]:
    """Summarized items per type from today's feed pass. Never raises — the
    briefing must render even if the feed db is missing or corrupt."""
    if not settings.feed_enabled:
        return {}
    counts: dict[str, int] = {}
    try:
        from secondbrain.stores.feed import FeedStore

        # Only today's refresh counts. An all-time top-N would report the same
        # numbers every morning — including on days the fetch failed entirely.
        cutoff = (
            datetime.now(UTC) - timedelta(hours=settings.feed_digest_window_hours)
        ).isoformat()
        store = FeedStore(Path(settings.data_path) / settings.feed_db_name)
        try:
            for row in store.get_summarized_since(cutoff, limit=settings.feed_top_n):
                counts[row["type"]] = counts.get(row["type"], 0) + 1
        finally:
            store.close()
    except Exception:
        logger.warning("Feed count lookup failed", exc_info=True)
    return counts


def _build_briefing(settings: Settings) -> BriefingResponse:
    """Assemble the morning briefing data."""
    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < _CACHE_TTL:  # type: ignore[operator]
        return _cache["data"]  # type: ignore[return-value]

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today.strftime("%Y-%m-%d")
    today_display = today.strftime("%A, %B %-d, %Y")

    vault_path = settings.vault_path
    if not vault_path or not vault_path.exists():
        raise HTTPException(status_code=503, detail="Vault path not configured or not found")

    daily_dir = vault_path / "00_Daily"

    # Aggregate tasks
    all_tasks = scan_daily_notes(daily_dir)
    aggregated = aggregate_tasks(all_tasks)
    open_tasks = [t for t in aggregated if not t.completed]

    # Categorize
    overdue: list[BriefingTask] = []
    due_today: list[BriefingTask] = []
    aging: list[BriefingTask] = []

    for t in open_tasks:
        bt = _to_briefing_task(t)
        if t.due_date and t.due_date < today_str:
            overdue.append(bt)
        elif t.due_date and t.due_date == today_str:
            due_today.append(bt)
        elif not t.due_date and t.days_open > 3 and t.status == "open":
            aging.append(bt)

    # Sort: overdue by due_date asc, aging by days_open desc
    overdue.sort(key=lambda t: t.due_date)
    aging.sort(key=lambda t: t.days_open, reverse=True)

    # Yesterday's context — strict yesterday only (no multi-day lookback)
    yesterday_ctx = find_recent_daily_context(daily_dir, lookback_days=0)
    daily_context = DailyContext(**asdict(yesterday_ctx)) if yesterday_ctx else None

    # Today's context — focus/notes from today's daily note
    today_ctx_raw = parse_daily_note_sections(daily_dir, today_str)
    today_context = DailyContext(**asdict(today_ctx_raw)) if today_ctx_raw else None

    # Today's events
    raw_events = get_events_in_range(daily_dir, today.date(), today.date())
    today_events = [
        EventResponse(
            title=e.title,
            date=e.date,
            time=e.time,
            end_date=e.end_date,
            source_file=e.source_file,
        )
        for e in raw_events
    ]

    result = BriefingResponse(
        today=today_str,
        today_display=today_display,
        overdue_tasks=overdue,
        due_today_tasks=due_today,
        aging_followups=aging,
        yesterday_context=daily_context,
        today_context=today_context,
        today_events=today_events,
        total_open=len(open_tasks),
        feed_counts=_feed_counts(settings),
    )

    _cache["data"] = result
    _cache["ts"] = now
    return result


def _short_date(today_iso: str) -> str:
    """Format an ISO date (YYYY-MM-DD) as a compact label, e.g. 'Aug 2'."""
    try:
        d = datetime.strptime(today_iso, "%Y-%m-%d")
    except ValueError:
        return today_iso
    return d.strftime("%b %-d")


def _build_digest(briefing: BriefingResponse) -> DigestResponse:
    """Reduce a briefing to a compact push digest.

    Pure projection: no I/O. ``count`` is the number of items worth surfacing;
    when zero, the body is a neutral all-clear so the notifier can stay quiet.
    """
    overdue = len(briefing.overdue_tasks)
    due = len(briefing.due_today_tasks)
    aging = len(briefing.aging_followups)
    feed_total = sum(briefing.feed_counts.values())
    count = overdue + due + aging + feed_total

    title = f"SecondBrain · {_short_date(briefing.today)}"

    if count == 0:
        return DigestResponse(title=title, body="All clear — nothing needs attention.", count=0)

    segments: list[str] = []
    if overdue:
        segments.append(f"{overdue} overdue")
    if due:
        segments.append(f"{due} due today")
    if aging:
        segments.append(f"{aging} aging follow-up{'s' if aging != 1 else ''}")
    ai = briefing.feed_counts.get("ai", 0)
    sports = briefing.feed_counts.get("sports", 0)
    if ai:
        segments.append(f"{ai} AI update{'s' if ai != 1 else ''}")
    if sports:
        segments.append(f"{sports} sports")
    # Catch-all so any other feed type still earns a segment: without it a
    # "general" item would raise count above zero with an empty body.
    other = sum(c for t, c in briefing.feed_counts.items() if t not in ("ai", "sports"))
    if other:
        segments.append(f"{other} more")

    return DigestResponse(title=title, body=" · ".join(segments), count=count)


@router.get("/briefing", response_model=BriefingResponse)
async def get_briefing(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BriefingResponse:
    """Get the morning briefing: overdue tasks, due today, aging follow-ups, and yesterday's context."""
    return await asyncio.to_thread(_build_briefing, settings)


@router.get("/digest", response_model=DigestResponse)
async def get_digest(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DigestResponse:
    """Compact push digest for a scheduled iOS Shortcut (title, one-line body, count).

    The shared re-engagement channel: future ENGAGE/FEED sections fold their
    counts into the same one-liner. ``count == 0`` means the notifier stays quiet.
    """
    briefing = await asyncio.to_thread(_build_briefing, settings)
    return _build_digest(briefing)
