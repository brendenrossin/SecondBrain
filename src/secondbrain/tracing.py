"""OTel tracing initialization for TraceEval integration."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from opentelemetry import trace
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
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        path = self._traces_dir / f"{today}.jsonl"
        try:
            with open(path, "a", encoding="utf-8") as f:
                for span in spans:
                    f.write(json.dumps(json.loads(span.to_json())) + "\n")
            return SpanExportResult.SUCCESS
        except Exception:
            logger.exception("Failed to export spans to %s", path)
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass


def _create_langfuse_processor(
    public_key: str,
    secret_key: str,
    host: str,
) -> object:
    """Create a LangfuseSpanProcessor. Lazy import to avoid cost when unused."""
    from langfuse.opentelemetry import LangfuseSpanProcessor

    return LangfuseSpanProcessor(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
    )


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

    # Add Langfuse exporter if keys are configured (dual-write)
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        try:
            processor = _create_langfuse_processor(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            provider = trace.get_tracer_provider()
            provider.add_span_processor(processor)  # type: ignore[attr-defined]
            logger.info("Langfuse tracing enabled — sending spans to %s", settings.langfuse_host)
        except Exception:
            logger.exception("Failed to initialize Langfuse exporter — continuing with JSONL only")
