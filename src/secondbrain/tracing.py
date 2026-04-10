"""OTel tracing initialization for TraceEval integration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from traceloop.sdk import Traceloop

from secondbrain.config import Settings

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


def init_tracing(settings: Settings) -> None:
    """Initialize OTel tracing if enabled. Call once at app startup."""
    if not settings.tracing_enabled:
        return

    traces_dir = Path(settings.data_path) / "traces"
    exporter = FileSpanExporter(traces_dir)

    Traceloop.init(
        app_name="secondbrain",
        exporter=exporter,
    )

    logger.info("OTel tracing enabled — writing spans to %s", traces_dir)
