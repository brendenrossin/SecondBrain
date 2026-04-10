"""OTel tracing initialization for TraceEval integration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan

logger = logging.getLogger(__name__)


class FileSpanExporter(SpanExporter):
    """Exports OTel spans as JSONL files, one per UTC day."""

    def __init__(self, traces_dir: Path) -> None:
        self._traces_dir = traces_dir
        self._traces_dir.mkdir(parents=True, exist_ok=True)

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._traces_dir / f"{today}.jsonl"
        try:
            with open(path, "a") as f:
                for span in spans:
                    f.write(json.dumps(json.loads(span.to_json())) + "\n")
            return SpanExportResult.SUCCESS
        except Exception:
            logger.exception("Failed to export spans to %s", path)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass
