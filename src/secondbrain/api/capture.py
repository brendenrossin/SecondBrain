"""Quick capture endpoint: write text directly to the Inbox folder."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from secondbrain.api.dependencies import get_settings
from secondbrain.models import CaptureRequest, CaptureResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["capture"])


@router.post("/capture", response_model=CaptureResponse)
async def capture(request: CaptureRequest) -> CaptureResponse:
    """Write captured text to the Inbox as a timestamped Markdown file.

    The file will be picked up by the inbox processor on the next sync.
    """
    settings = get_settings()
    if not settings.vault_path:
        raise HTTPException(status_code=500, detail="SECONDBRAIN_VAULT_PATH not configured")

    inbox_dir = settings.vault_path / "Inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%d_%H%M%S")
    filename = f"capture_{timestamp}.md"
    filepath = inbox_dir / filename

    # Avoid overwriting if two captures happen in the same second
    if filepath.exists():
        filename = f"capture_{timestamp}_{now.microsecond}.md"
        filepath = inbox_dir / filename

    filepath.write_text(request.text, encoding="utf-8")
    logger.info("Captured to %s (%d chars)", filename, len(request.text))

    return CaptureResponse(
        filename=filename,
        message=f"Captured to Inbox/{filename}",
    )
