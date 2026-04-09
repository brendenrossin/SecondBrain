"""Admin endpoints for cost tracking, traces, and system stats."""

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from secondbrain.api.dependencies import (
    get_conversation_store,
    get_index_tracker,
    get_query_logger,
    get_settings,
    get_usage_store,
)
from secondbrain.config import Settings
from secondbrain.logging.query_logger import QueryLogger
from secondbrain.models import (
    AdminStatsResponse,
    AnomalyAlert,
    CostSummaryResponse,
    DailyCost,
    DailyCostsResponse,
    TraceEntry,
    UsageCostBreakdown,
)
from secondbrain.stores.conversation import ConversationStore
from secondbrain.stores.index_tracker import IndexTracker
from secondbrain.stores.usage import UsageStore

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/costs", response_model=CostSummaryResponse)
async def get_costs(
    usage_store: Annotated[UsageStore, Depends(get_usage_store)],
    period: str = Query(default="week", pattern="^(week|month|all)$"),
) -> CostSummaryResponse:
    """Get aggregated cost summary for a time period."""
    since = None
    if period == "week":
        since = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    elif period == "month":
        since = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    summary = usage_store.get_summary(since=since)

    return CostSummaryResponse(
        total_cost=summary["total_cost"],
        total_calls=summary["total_calls"],
        by_provider={k: UsageCostBreakdown(**v) for k, v in summary["by_provider"].items()},
        by_usage_type={k: UsageCostBreakdown(**v) for k, v in summary["by_usage_type"].items()},
        period=period,
    )


@router.get("/costs/daily", response_model=DailyCostsResponse)
async def get_daily_costs(
    usage_store: Annotated[UsageStore, Depends(get_usage_store)],
    days: int = Query(default=30, ge=1, le=365),
) -> DailyCostsResponse:
    """Get daily cost breakdown."""
    daily = usage_store.get_daily_costs(days=days)

    return DailyCostsResponse(
        days=days,
        daily=[DailyCost(**d) for d in daily],
    )


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    usage_store: Annotated[UsageStore, Depends(get_usage_store)],
    query_logger: Annotated[QueryLogger, Depends(get_query_logger)],
    conversation_store: Annotated[ConversationStore, Depends(get_conversation_store)],
    index_tracker: Annotated[IndexTracker, Depends(get_index_tracker)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdminStatsResponse:
    """Get system-wide admin statistics."""
    query_stats = query_logger.get_stats()
    usage_summary = usage_store.get_summary()
    total_conversations = conversation_store.count_conversations()
    index_stats = index_tracker.get_stats()

    total_queries = query_stats.get("total_queries", 0)
    avg_latency = query_stats.get("avg_latency_ms", 0)
    file_count = index_stats.get("file_count", 0)

    # Today's cost and call count
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    today_data = usage_store.get_daily_costs(days=1)
    today_entry = next((d for d in today_data if d["date"] == today_str), None)
    today_cost = today_entry["cost_usd"] if today_entry else 0.0
    today_calls = today_entry["calls"] if today_entry else 0

    # Cost alert if today exceeds threshold
    threshold = settings.cost_alert_threshold
    cost_alert = None
    if today_cost >= threshold:
        cost_alert = f"Today's LLM cost (${today_cost:.2f}) exceeds ${threshold:.2f} threshold"

    # Anomaly detection
    anomalies_raw = usage_store.get_anomalies()
    anomalies = [AnomalyAlert(**a) for a in anomalies_raw]

    return AdminStatsResponse(
        total_queries=total_queries if isinstance(total_queries, int) else 0,
        avg_latency_ms=float(avg_latency) if isinstance(avg_latency, (int, float)) else 0.0,
        total_conversations=total_conversations,
        index_file_count=file_count if isinstance(file_count, int) else 0,
        total_llm_calls=usage_summary["total_calls"],
        total_llm_cost=usage_summary["total_cost"],
        today_cost=today_cost,
        today_calls=today_calls,
        cost_alert=cost_alert,
        anomalies=anomalies,
    )


@router.get("/traces", response_model=list[TraceEntry])
async def get_traces(
    usage_store: Annotated[UsageStore, Depends(get_usage_store)],
    limit: int = Query(default=50, ge=1, le=200),
    usage_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Get recent LLM call traces with full details."""
    return usage_store.get_traces(limit=limit, usage_type=usage_type, status=status, since=since)


@router.get("/traces/{trace_id}", response_model=list[TraceEntry])
async def get_trace_group(
    trace_id: str,
    usage_store: Annotated[UsageStore, Depends(get_usage_store)],
) -> list[dict[str, Any]]:
    """Get all calls sharing a trace_id."""
    return usage_store.get_trace_group(trace_id)


@router.get("/sync-status")
async def sync_status(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Get the status of the last daily sync."""
    data_path = Path(settings.data_path)
    result: dict[str, Any] = {"last_sync": None, "status": "unknown"}

    completed = data_path / ".sync_completed"
    failed = data_path / ".sync_failed"

    if completed.exists():
        mtime = completed.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        result["last_sync"] = completed.read_text().strip()
        result["status"] = "stale" if age_hours > 25 else "ok"
        result["hours_ago"] = round(age_hours, 1)

    if failed.exists() and (
        not completed.exists() or failed.stat().st_mtime > completed.stat().st_mtime
    ):
        result["status"] = "failed"
        result["error"] = failed.read_text().strip()

    return result
