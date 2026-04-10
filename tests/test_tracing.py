"""Tests for OTel tracing initialization and JSONL span export."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from opentelemetry.sdk.trace.export import SpanExportResult

from secondbrain.config import Settings


def test_tracing_disabled_by_default():
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
    )
    assert settings.tracing_enabled is False


def test_file_span_exporter_creates_directory(tmp_path):
    from secondbrain.tracing import FileSpanExporter

    traces_dir = tmp_path / "traces"
    exporter = FileSpanExporter(traces_dir)
    assert traces_dir.exists()


def test_file_span_exporter_writes_jsonl(tmp_path):
    from secondbrain.tracing import FileSpanExporter

    traces_dir = tmp_path / "traces"
    exporter = FileSpanExporter(traces_dir)

    span = MagicMock()
    span.to_json.return_value = '{"name": "test_span", "trace_id": "abc123"}'

    result = exporter.export([span])

    assert result == SpanExportResult.SUCCESS
    files = list(traces_dir.glob("*.jsonl"))
    assert len(files) == 1
    assert files[0].name.endswith(".jsonl")
    from datetime import datetime, timezone
    expected_name = datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"
    assert files[0].name == expected_name
    lines = files[0].read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["name"] == "test_span"


def test_file_span_exporter_appends_multiple_spans(tmp_path):
    from secondbrain.tracing import FileSpanExporter

    traces_dir = tmp_path / "traces"
    exporter = FileSpanExporter(traces_dir)

    span1 = MagicMock()
    span1.to_json.return_value = '{"name": "span1"}'
    span2 = MagicMock()
    span2.to_json.return_value = '{"name": "span2"}'

    exporter.export([span1])
    exporter.export([span2])

    files = list(traces_dir.glob("*.jsonl"))
    lines = files[0].read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["name"] == "span1"
    assert json.loads(lines[1])["name"] == "span2"


def test_file_span_exporter_handles_write_error(tmp_path):
    from secondbrain.tracing import FileSpanExporter

    traces_dir = tmp_path / "traces"
    exporter = FileSpanExporter(traces_dir)

    span = MagicMock()
    span.to_json.side_effect = Exception("serialization error")

    result = exporter.export([span])
    assert result == SpanExportResult.FAILURE
