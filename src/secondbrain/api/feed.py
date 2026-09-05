"""Feed API — list ranked items + record clicks.

Read path only: refreshing the feed is cron-driven via `daily_sync feed`, so a
page load never triggers a fetch or an LLM call.
"""

import asyncio
import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from secondbrain.api.dependencies import get_settings
from secondbrain.config import Settings
from secondbrain.models import FeedItemResponse, FeedResponse, FeedSectionResponse
from secondbrain.stores.feed import FeedStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["feed"])

_FEED_LIMIT = 50


def _store(settings: Settings) -> FeedStore:
    return FeedStore(Path(settings.data_path) / settings.feed_db_name)


def _fetch_recent(settings: Settings) -> list[dict[str, Any]]:
    store = _store(settings)
    try:
        return store.get_recent(limit=_FEED_LIMIT)
    finally:
        store.close()


def _to_item(row: dict[str, Any]) -> FeedItemResponse:
    return FeedItemResponse(
        id=row["id"],
        url=row["url"],
        source_label=row["source_label"],
        type=row["type"],
        title=row["title"],
        snippet=row["snippet"] or "",
        summary=row["summary"],
        score=row["score"],
        published_at=row["published_at"],
    )


def _to_sections(rows: list[dict[str, Any]]) -> list[FeedSectionResponse]:
    """Group summarized items by type; unsummarized items appear only in `items`."""
    by_type: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row["summary"]:
            by_type.setdefault(row["type"], []).append(
                {"url": row["url"], "title": row["title"], "take": row["summary"]}
            )
    return [FeedSectionResponse(heading=t.upper(), items=v) for t, v in by_type.items()]


@router.get("/feed", response_model=FeedResponse)
async def get_feed(settings: Annotated[Settings, Depends(get_settings)]) -> FeedResponse:
    """Ranked feed items, plus summarized sections when the daily pass produced takes."""
    if not settings.feed_enabled:
        return FeedResponse(generated=False, sections=[], items=[])
    rows = await asyncio.to_thread(_fetch_recent, settings)
    sections = _to_sections(rows)
    return FeedResponse(
        generated=bool(sections),
        sections=sections,
        items=[_to_item(row) for row in rows],
    )


@router.post("/feed/{item_id}/click")
async def record_click(
    item_id: int, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, str]:
    """Record engagement and hand back the target URL. Feeds interest tuning in FEED-2."""

    def _click() -> str | None:
        store = _store(settings)
        try:
            return store.mark_clicked(item_id)
        finally:
            store.close()

    url = await asyncio.to_thread(_click)
    if url is None:
        raise HTTPException(status_code=404, detail="Feed item not found")
    return {"url": url}
