"""Calendar events API endpoints."""

import logging
import time
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from secondbrain.api.dependencies import get_settings
from secondbrain.config import Settings
from secondbrain.models import EventResponse
from secondbrain.scripts.event_parser import get_events_in_range

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["events"])

# Simple TTL cache for events
_cache: dict[str, object] = {"data": None, "ts": 0.0, "key": ""}
_CACHE_TTL = 60.0  # seconds


@router.get("/events", response_model=list[EventResponse])
async def list_events(
    settings: Annotated[Settings, Depends(get_settings)],
    start: str = Query(description="Start date YYYY-MM-DD"),
    end: str = Query(description="End date YYYY-MM-DD"),
) -> list[EventResponse]:
    """List calendar events in a date range."""
    cache_key = f"{start}:{end}"
    now = time.time()
    if (
        _cache["data"] is not None
        and (now - _cache["ts"]) < _CACHE_TTL  # type: ignore[operator]
        and _cache["key"] == cache_key
    ):
        return _cache["data"]  # type: ignore[return-value]

    vault_path = settings.vault_path
    if not vault_path or not vault_path.exists():
        return []

    daily_dir = vault_path / "00_Daily"

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    events = get_events_in_range(daily_dir, start_date, end_date)

    result = [
        EventResponse(
            title=e.title,
            date=e.date,
            time=e.time,
            end_date=e.end_date,
            source_file=e.source_file,
        )
        for e in events
    ]

    _cache["data"] = result
    _cache["ts"] = now
    _cache["key"] = cache_key
    return result
