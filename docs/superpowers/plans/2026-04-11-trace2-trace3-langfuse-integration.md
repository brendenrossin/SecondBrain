# TRACE-2 + TRACE-3: Langfuse Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Langfuse as a second trace destination alongside JSONL, giving a web-based trace viewer UI with zero changes to LLM call sites.

**Architecture:** After `Traceloop.init()` creates the global `TracerProvider` with our `FileSpanExporter`, we add a `LangfuseSpanProcessor` to that same provider. Both processors receive every span. Langfuse keys are optional — if absent, behavior is unchanged.

**Tech Stack:** `langfuse` Python SDK (includes `LangfuseSpanProcessor`), existing `opentelemetry-sdk`, existing `traceloop-sdk`

---

### Task 1: Add `langfuse` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add langfuse to project dependencies**

In `pyproject.toml`, add `langfuse` to the `dependencies` list:

```toml
"langfuse>=3.0.0",
```

Add it after the existing `traceloop-sdk` entry.

- [ ] **Step 2: Sync and verify install**

Run: `uv sync`
Expected: langfuse and its dependencies install without error

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add langfuse dependency for TRACE-2"
```

---

### Task 2: Add Langfuse config fields

**Files:**
- Modify: `src/secondbrain/config.py`
- Test: `tests/test_tracing.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tracing.py`:

```python
def test_langfuse_config_defaults():
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
    )
    assert settings.langfuse_public_key == ""
    assert settings.langfuse_secret_key == ""
    assert settings.langfuse_host == "https://cloud.langfuse.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tracing.py::test_langfuse_config_defaults -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'langfuse_public_key'`

- [ ] **Step 3: Add config fields**

In `src/secondbrain/config.py`, add these fields to the `Settings` class after the `tracing_enabled` field. Note: these use the `LANGFUSE_` prefix (no `SECONDBRAIN_` prefix) since Langfuse SDKs conventionally look for these exact env var names.

```python
    # Langfuse (trace viewer UI) — keys from cloud.langfuse.com project settings
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
```

Also update the `SettingsConfigDict` to allow the `LANGFUSE_` prefix by adding an `alias_generator` or — simpler — add explicit `Field` aliases. Actually, the simplest approach: since `pydantic-settings` uses the `env_prefix` for all fields, these would become `SECONDBRAIN_LANGFUSE_PUBLIC_KEY`. But Langfuse's SDK also reads `LANGFUSE_PUBLIC_KEY` directly. Let's keep it simple and use `SECONDBRAIN_LANGFUSE_*` for our config, and separately pass the values to Langfuse. This is consistent with how we handle `SECONDBRAIN_OPENAI_API_KEY` etc.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tracing.py::test_langfuse_config_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/config.py tests/test_tracing.py
git commit -m "feat(trace): add Langfuse config fields to Settings"
```

---

### Task 3: Add Langfuse exporter to tracing init

**Files:**
- Modify: `src/secondbrain/tracing.py`
- Test: `tests/test_tracing.py`

- [ ] **Step 1: Write the failing test for dual-export**

Add to `tests/test_tracing.py`:

```python
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
        patch("secondbrain.tracing.LangfuseSpanProcessor") as mock_langfuse_proc,
        patch("secondbrain.tracing.trace") as mock_trace,
    ):
        mock_provider = MagicMock()
        mock_trace.get_tracer_provider.return_value = mock_provider

        init_tracing(settings)

        mock_traceloop.init.assert_called_once()
        mock_langfuse_proc.assert_called_once()
        mock_provider.add_span_processor.assert_called_once()
```

- [ ] **Step 2: Write the failing test for JSONL-only fallback**

Add to `tests/test_tracing.py`:

```python
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
        patch("secondbrain.tracing.trace") as mock_trace,
    ):
        mock_provider = MagicMock()
        mock_trace.get_tracer_provider.return_value = mock_provider

        init_tracing(settings)

        mock_traceloop.init.assert_called_once()
        mock_provider.add_span_processor.assert_not_called()
```

- [ ] **Step 3: Write the failing test for graceful Langfuse init failure**

Add to `tests/test_tracing.py`:

```python
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
        patch("secondbrain.tracing.LangfuseSpanProcessor", side_effect=Exception("connection failed")),
        patch("secondbrain.tracing.trace"),
    ):
        # Should not raise — graceful degradation to JSONL only
        init_tracing(settings)
        mock_traceloop.init.assert_called_once()
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_tracing.py::test_init_tracing_adds_langfuse_when_keys_present tests/test_tracing.py::test_init_tracing_skips_langfuse_when_no_keys tests/test_tracing.py::test_init_tracing_handles_langfuse_init_failure -v`
Expected: FAIL (LangfuseSpanProcessor not imported, trace not imported)

- [ ] **Step 5: Implement dual-export in tracing.py**

Replace the contents of `src/secondbrain/tracing.py` with:

```python
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

# Lazy import — only needed when Langfuse keys are configured
LangfuseSpanProcessor = None


def _get_langfuse_span_processor():
    """Lazy import LangfuseSpanProcessor to avoid import cost when unused."""
    global LangfuseSpanProcessor
    if LangfuseSpanProcessor is None:
        from langfuse.opentelemetry import LangfuseSpanProcessor as _LangfuseSpanProcessor
        LangfuseSpanProcessor = _LangfuseSpanProcessor
    return LangfuseSpanProcessor


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

    # Add Langfuse exporter if keys are configured
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        try:
            LangfuseProc = _get_langfuse_span_processor()
            processor = LangfuseProc(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            provider = trace.get_tracer_provider()
            provider.add_span_processor(processor)
            logger.info("Langfuse tracing enabled — sending spans to %s", settings.langfuse_host)
        except Exception:
            logger.exception("Failed to initialize Langfuse exporter — continuing with JSONL only")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_tracing.py -v`
Expected: All tests PASS (existing + 4 new)

Note: The tests mock `LangfuseSpanProcessor` at the module level. Update the test imports and patches to account for the lazy import pattern. The patches should target `secondbrain.tracing._get_langfuse_span_processor` or mock the module-level `LangfuseSpanProcessor` variable. Adjust as needed if the mock paths need updating.

- [ ] **Step 7: Run full check**

Run: `make check`
Expected: All lint, typecheck, and tests pass

- [ ] **Step 8: Commit**

```bash
git add src/secondbrain/tracing.py tests/test_tracing.py
git commit -m "feat(trace): add Langfuse dual-export to tracing init (TRACE-2)"
```

---

### Task 4: Update ROADMAP and docs

**Files:**
- Modify: `docs/ROADMAP.md`
- Modify: `docs/traceeval-integration/README.md`

- [ ] **Step 1: Update traceeval-integration README**

In `docs/traceeval-integration/README.md`, update the Phase 9.8b row status from "Future" to "Done" and add a note about the implementation.

- [ ] **Step 2: Update ROADMAP.md**

Update TRACE-3's description to note it's covered by TRACE-2's platform-agnostic OTel architecture.

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md docs/traceeval-integration/README.md
git commit -m "docs: update tracing docs for TRACE-2 Langfuse integration"
```

---

### Task 5: Integration verification

- [ ] **Step 1: Verify tracing works end-to-end without Langfuse keys**

Ensure `SECONDBRAIN_TRACING_ENABLED=true` is set but no `LANGFUSE_*` keys are in `.env`. Restart the API server and make a query. Verify:
- JSONL trace file created in `data/traces/`
- No Langfuse errors in logs
- Server log shows "OTel tracing enabled" but NOT "Langfuse tracing enabled"

- [ ] **Step 2: Verify with Langfuse keys (if available)**

If the user has set up Langfuse keys in `.env`, restart the API and make a query. Verify:
- Server log shows both "OTel tracing enabled" and "Langfuse tracing enabled"
- JSONL trace file still created
- Traces appear in Langfuse dashboard

- [ ] **Step 3: Run make check one final time**

Run: `make check`
Expected: All clean
