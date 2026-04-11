"""Tests for OTel tracing initialization and JSONL span export."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from opentelemetry.sdk.trace.export import SpanExportResult

from secondbrain.config import Settings
from secondbrain.tracing import FileSpanExporter, init_tracing


def test_tracing_disabled_by_default():
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
    )
    assert settings.tracing_enabled is False


def test_file_span_exporter_creates_directory(tmp_path):
    traces_dir = tmp_path / "traces"
    FileSpanExporter(traces_dir)
    assert traces_dir.exists()


def test_file_span_exporter_writes_jsonl(tmp_path):
    traces_dir = tmp_path / "traces"
    exporter = FileSpanExporter(traces_dir)

    span = MagicMock()
    span.to_json.return_value = '{"name": "test_span", "trace_id": "abc123"}'

    result = exporter.export([span])

    assert result == SpanExportResult.SUCCESS
    files = list(traces_dir.glob("*.jsonl"))
    assert len(files) == 1
    assert files[0].name.endswith(".jsonl")
    expected_name = datetime.now(UTC).strftime("%Y-%m-%d") + ".jsonl"
    assert files[0].name == expected_name
    lines = files[0].read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["name"] == "test_span"


def test_file_span_exporter_appends_multiple_spans(tmp_path):
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
    traces_dir = tmp_path / "traces"
    exporter = FileSpanExporter(traces_dir)

    span = MagicMock()
    span.to_json.side_effect = Exception("serialization error")

    result = exporter.export([span])
    assert result == SpanExportResult.FAILURE


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
        assert isinstance(call_kwargs.kwargs.get("exporter"), FileSpanExporter)
    assert (tmp_path / "traces").exists()


# --- Langfuse integration tests ---


def test_langfuse_config_defaults(monkeypatch):
    monkeypatch.setenv("SECONDBRAIN_LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("SECONDBRAIN_LANGFUSE_SECRET_KEY", "")
    monkeypatch.setenv("SECONDBRAIN_LANGFUSE_HOST", "https://cloud.langfuse.com")
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
    )
    assert settings.langfuse_public_key == ""
    assert settings.langfuse_secret_key == ""
    assert settings.langfuse_host == "https://cloud.langfuse.com"


def test_init_tracing_adds_langfuse_when_keys_present(tmp_path):
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
        tracing_enabled=True,
        data_path=tmp_path,
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key="sk-lf-test",
        langfuse_host="https://cloud.langfuse.com",
    )
    with (
        patch("secondbrain.tracing.Traceloop") as mock_traceloop,
        patch("secondbrain.tracing._create_langfuse_otlp_processor") as mock_create,
        patch("secondbrain.tracing.trace") as mock_trace,
    ):
        mock_processor = MagicMock()
        mock_create.return_value = mock_processor
        mock_provider = MagicMock()
        mock_trace.get_tracer_provider.return_value = mock_provider

        init_tracing(settings)

        mock_traceloop.init.assert_called_once()
        mock_create.assert_called_once_with(
            public_key="pk-lf-test",
            secret_key="sk-lf-test",
            host="https://cloud.langfuse.com",
        )
        mock_provider.add_span_processor.assert_called_once_with(mock_processor)


def test_init_tracing_skips_langfuse_when_no_keys(tmp_path):
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
        tracing_enabled=True,
        data_path=tmp_path,
        langfuse_public_key="",
        langfuse_secret_key="",
    )
    with (
        patch("secondbrain.tracing.Traceloop") as mock_traceloop,
        patch("secondbrain.tracing._create_langfuse_otlp_processor") as mock_create,
    ):
        init_tracing(settings)

        mock_traceloop.init.assert_called_once()
        mock_create.assert_not_called()


def test_init_tracing_handles_langfuse_init_failure(tmp_path):
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
        tracing_enabled=True,
        data_path=tmp_path,
        langfuse_public_key="pk-lf-bad",
        langfuse_secret_key="sk-lf-bad",
    )
    with (
        patch("secondbrain.tracing.Traceloop") as mock_traceloop,
        patch(
            "secondbrain.tracing._create_langfuse_otlp_processor",
            side_effect=Exception("connection failed"),
        ),
    ):
        # Should not raise — graceful degradation to JSONL only
        init_tracing(settings)
        mock_traceloop.init.assert_called_once()


def test_main_calls_init_tracing():
    """Verify main.py lifespan calls init_tracing."""
    import ast

    main_path = Path(__file__).parent.parent / "src" / "secondbrain" / "main.py"
    source = main_path.read_text()
    tree = ast.parse(source)

    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    tracing_imported = any(getattr(node, "module", "") == "secondbrain.tracing" for node in imports)
    assert tracing_imported, "main.py must import from secondbrain.tracing"
    assert "init_tracing" in source, "main.py must call init_tracing"


def test_daily_sync_calls_init_tracing():
    """Verify daily_sync.py calls init_tracing."""
    source_path = Path(__file__).parent.parent / "src" / "secondbrain" / "scripts" / "daily_sync.py"
    source = source_path.read_text()
    assert "init_tracing" in source, "daily_sync.py must call init_tracing"


def test_inbox_processor_calls_init_tracing():
    """Verify inbox_processor.py calls init_tracing."""
    source_path = (
        Path(__file__).parent.parent / "src" / "secondbrain" / "scripts" / "inbox_processor.py"
    )
    source = source_path.read_text()
    assert "init_tracing" in source, "inbox_processor.py must call init_tracing"
