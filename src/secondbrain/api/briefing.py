"""Morning briefing API endpoint."""

import logging
import time
from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from secondbrain.api.dependencies import get_settings
from secondbrain.config import Settings
from secondbrain.models import BriefingResponse, BriefingTask, DailyContext, EventResponse
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
        return BriefingResponse(
            today=today_str,
            today_display=today_display,
            overdue_tasks=[],
            due_today_tasks=[],
            aging_followups=[],
            yesterday_context=None,
            today_context=None,
            today_events=[],
            total_open=0,
        )

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
    )

    _cache["data"] = result
    _cache["ts"] = now
    return result


@router.get("/briefing", response_model=BriefingResponse)
async def get_briefing(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BriefingResponse:
    """Get the morning briefing: overdue tasks, due today, aging follow-ups, and yesterday's context."""
    return _build_briefing(settings)
