"""Task aggregation API endpoints."""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from secondbrain.api.dependencies import get_settings
from secondbrain.config import Settings
from secondbrain.models import TaskResponse, TaskUpdateRequest
from secondbrain.scripts.task_aggregator import (
    aggregate_tasks,
    scan_daily_notes,
    update_task_in_daily,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["tasks"])

# Simple TTL cache for aggregated tasks
_cache: dict[str, object] = {"data": None, "ts": 0.0}
_CACHE_TTL = 60.0  # seconds


def _get_aggregated(settings: Settings) -> list[TaskResponse]:
    """Get aggregated tasks, with TTL cache."""
    now = time.time()
    if _cache["data"] is not None and (now - _cache["ts"]) < _CACHE_TTL:  # type: ignore[operator]
        return _cache["data"]  # type: ignore[return-value]

    vault_path = settings.vault_path
    if not vault_path or not vault_path.exists():
        return []

    daily_dir = vault_path / "00_Daily"
    all_tasks = scan_daily_notes(daily_dir)
    aggregated = aggregate_tasks(all_tasks)

    result = [
        TaskResponse(
            text=t.text,
            category=t.category,
            sub_project=t.sub_project,
            due_date=t.due_date,
            completed=t.completed,
            status=t.status,
            days_open=t.days_open,
            first_date=t.first_date,
            latest_date=t.latest_date,
            appearance_count=len(t.appearances),
        )
        for t in aggregated
    ]

    _cache["data"] = result
    _cache["ts"] = now
    return result


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    settings: Annotated[Settings, Depends(get_settings)],
    category: str | None = None,
    completed: bool | None = None,
    status: str | None = None,
    sub_project: str | None = None,
) -> list[TaskResponse]:
    """List all aggregated tasks with optional filters."""
    tasks = _get_aggregated(settings)

    if category is not None:
        tasks = [t for t in tasks if t.category == category]
    if completed is not None:
        tasks = [t for t in tasks if t.completed == completed]
    if status is not None:
        tasks = [t for t in tasks if t.status == status]
    if sub_project is not None:
        tasks = [t for t in tasks if t.sub_project == sub_project]

    return tasks


@router.patch("/tasks/update", response_model=TaskResponse)
async def update_task(
    req: TaskUpdateRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TaskResponse:
    """Update a task's status or due date in the vault."""
    vault_path = settings.vault_path
    if not vault_path or not vault_path.exists():
        raise HTTPException(status_code=500, detail="Vault path not configured")

    result = update_task_in_daily(
        vault_path=vault_path,
        text=req.text,
        category=req.category,
        sub_project=req.sub_project,
        status=req.status,
        due_date=req.due_date,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Task not found in daily notes")

    # Invalidate cache
    _cache["data"] = None

    return result


@router.get("/tasks/upcoming", response_model=list[TaskResponse])
async def upcoming_tasks(
    settings: Annotated[Settings, Depends(get_settings)],
    days: int = Query(default=7, ge=1, le=90),
) -> list[TaskResponse]:
    """Get tasks due in the next N days, plus overdue tasks."""
    from datetime import datetime, timedelta

    tasks = _get_aggregated(settings)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = (today + timedelta(days=days)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    return [
        t
        for t in tasks
        if not t.completed and t.due_date and (t.due_date < today_str or t.due_date <= cutoff)
    ]


@router.get("/tasks/categories")
async def task_categories(
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[dict[str, object]]:
    """List categories with sub-projects and task counts."""
    tasks = _get_aggregated(settings)
    open_tasks = [t for t in tasks if not t.completed]

    cats: dict[str, dict[str, int]] = {}
    for t in open_tasks:
        cat = t.category or "Uncategorized"
        sub = t.sub_project or ""
        cats.setdefault(cat, {})
        cats[cat][sub] = cats[cat].get(sub, 0) + 1

    return [
        {
            "category": cat,
            "sub_projects": [
                {"name": name, "count": count} for name, count in sorted(subs.items())
            ],
            "total": sum(subs.values()),
        }
        for cat, subs in sorted(cats.items())
    ]
