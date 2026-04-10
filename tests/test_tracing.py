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


from unittest.mock import patch

from secondbrain.tracing import init_tracing, FileSpanExporter


def test_init_tracing_noop_when_disabled(tmp_path):
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
        tracing_enabled=False,
        data_path=tmp_path,
    )
    with patch("secondbrain.tracing.Traceloop") as mock_traceloop:
        init_tracing(settings)
        mock_traceloop.init.assert_not_called()


def test_init_tracing_initializes_when_enabled(tmp_path):
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
        tracing_enabled=True,
        data_path=tmp_path,
    )
    with patch("secondbrain.tracing.Traceloop") as mock_traceloop:
        init_tracing(settings)
        mock_traceloop.init.assert_called_once()
        call_kwargs = mock_traceloop.init.call_args
        # Should pass a FileSpanExporter instance
        assert isinstance(call_kwargs.kwargs.get("exporter"), FileSpanExporter)
    # Traces directory should be created
    assert (tmp_path / "traces").exists()
