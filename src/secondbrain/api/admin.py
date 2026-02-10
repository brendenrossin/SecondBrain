"""Admin endpoints for cost tracking and system stats."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from secondbrain.api.dependencies import (
    get_conversation_store,
    get_index_tracker,
    get_query_logger,
    get_usage_store,
)
from secondbrain.logging.query_logger import QueryLogger
from secondbrain.models import (
    AdminStatsResponse,
    CostSummaryResponse,
    DailyCost,
    DailyCostsResponse,
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
) -> AdminStatsResponse:
    """Get system-wide admin statistics."""
    query_stats = query_logger.get_stats()
    usage_summary = usage_store.get_summary()
    conversations = conversation_store.list_conversations(limit=10000)
    index_stats = index_tracker.get_stats()

    total_queries = query_stats.get("total_queries", 0)
    avg_latency = query_stats.get("avg_latency_ms", 0)
    file_count = index_stats.get("file_count", 0)

    return AdminStatsResponse(
        total_queries=total_queries if isinstance(total_queries, int) else 0,
        avg_latency_ms=float(avg_latency) if isinstance(avg_latency, (int, float)) else 0.0,
        total_conversations=len(conversations),
        index_file_count=file_count if isinstance(file_count, int) else 0,
        total_llm_calls=usage_summary["total_calls"],
        total_llm_cost=usage_summary["total_cost"],
    )
