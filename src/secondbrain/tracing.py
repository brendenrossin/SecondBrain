"""OTel tracing initialization."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from traceloop.sdk import Traceloop

from secondbrain.config import Settings

logger = logging.getLogger(__name__)

_LANGFUSE_PROBE_TIMEOUT = 1.5


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


def _langfuse_reachable(host: str) -> bool:
    """Whether anything is listening at `host`.

    Any HTTP response counts, including 401 or 404: the check is for a live
    listener, not a working route. Only a transport failure means "down".

    Worth the round trip because there is no cheaper signal. A
    `BatchSpanProcessor` aimed at a dead collector logs a full stack trace per
    flush from its own background thread, so it cannot be caught at the call
    site — and Langfuse runs in Docker, which is routinely not running.
    """
    try:
        httpx.get(host, timeout=_LANGFUSE_PROBE_TIMEOUT)
    except Exception:
        return False
    return True


def _create_langfuse_otlp_processor(
    public_key: str,
    secret_key: str,
    host: str,
) -> BatchSpanProcessor:
    """Create an OTLP exporter targeting Langfuse's OTel endpoint.

    Langfuse v4 accepts traces via standard OTLP/HTTP protocol with Basic Auth.
    """
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    endpoint = f"{host.rstrip('/')}/api/public/otel/v1/traces"

    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers={"Authorization": f"Basic {auth}"},
    )
    return BatchSpanProcessor(exporter)


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

    # Add Langfuse OTLP exporter if keys are configured (dual-write)
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        if not _langfuse_reachable(settings.langfuse_host):
            # Info, not warning: Langfuse is a viewer over the JSONL spans we
            # already wrote, and its Docker stack being down is an ordinary
            # state — nothing is lost and nothing needs doing.
            logger.info(
                "Langfuse not reachable at %s — tracing to JSONL only",
                settings.langfuse_host,
            )
            return
        try:
            processor = _create_langfuse_otlp_processor(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            provider = trace.get_tracer_provider()
            provider.add_span_processor(processor)  # type: ignore[attr-defined]
            logger.info("Langfuse tracing enabled — sending spans to %s", settings.langfuse_host)
        except Exception:
            logger.exception("Failed to initialize Langfuse exporter — continuing with JSONL only")
