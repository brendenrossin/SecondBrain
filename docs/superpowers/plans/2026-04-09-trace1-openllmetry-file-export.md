# TRACE-1: OpenLLMetry File Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OTel tracing to SecondBrain's LLM calls via traceloop-sdk, exporting spans as daily JSONL files for future eval tooling ingestion.

**Architecture:** Single new file `src/secondbrain/tracing.py` with a custom `FileSpanExporter` and `init_tracing()` function. traceloop-sdk auto-instruments OpenAI + Anthropic SDK clients via monkey-patching. Three integration points: FastAPI startup, daily_sync, inbox_processor.

**Tech Stack:** `traceloop-sdk`, `opentelemetry-sdk` (transitive), Python `pathlib`/`json`/`logging`

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/secondbrain/tracing.py` | `FileSpanExporter` + `init_tracing()` |
| Create | `tests/test_tracing.py` | Unit + integration tests for tracing |
| Modify | `src/secondbrain/config.py:58` | Add `tracing_enabled` field |
| Modify | `src/secondbrain/main.py:37` | Call `init_tracing()` in lifespan |
| Modify | `src/secondbrain/scripts/daily_sync.py:167` | Call `init_tracing()` after settings |
| Modify | `src/secondbrain/scripts/inbox_processor.py:230` | Call `init_tracing()` in `process_inbox()` |
| Modify | `pyproject.toml:7` | Add `traceloop-sdk` dependency |
| Modify | `.env` | Add `SECONDBRAIN_TRACING_ENABLED=true` |

---

### Task 1: Add `tracing_enabled` config field

**Files:**
- Modify: `src/secondbrain/config.py:58`
- Test: `tests/test_tracing.py` (new file)

- [ ] **Step 1: Write the failing test**

Create `tests/test_tracing.py`:

```python
"""Tests for OTel tracing initialization and JSONL span export."""

from secondbrain.config import Settings


def test_tracing_disabled_by_default():
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
    )
    assert settings.tracing_enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/test_tracing.py::test_tracing_disabled_by_default -v`
Expected: FAIL — `Settings` has no `tracing_enabled` field

- [ ] **Step 3: Add the config field**

In `src/secondbrain/config.py`, add after line 58 (`cost_alert_threshold`):

```python
    # Tracing
    tracing_enabled: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/test_tracing.py::test_tracing_disabled_by_default -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/config.py tests/test_tracing.py
git commit -m "feat(tracing): add tracing_enabled config field"
```

---

### Task 2: Add `traceloop-sdk` dependency

**Files:**
- Modify: `pyproject.toml:7`

- [ ] **Step 1: Add dependency to pyproject.toml**

In `pyproject.toml`, add to the `dependencies` list after the `anthropic` line (line 18):

```toml
    "traceloop-sdk>=0.53.0",
```

- [ ] **Step 2: Install the dependency**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv pip install -e ".[dev]"`
Expected: Successfully installs traceloop-sdk and its transitive deps (opentelemetry-sdk, etc.)

- [ ] **Step 3: Verify import works**

Run: `cd /Users/brentrossin/SecondBrain && python -c "from traceloop.sdk import Traceloop; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(tracing): add traceloop-sdk dependency"
```

---

### Task 3: Implement `FileSpanExporter`

**Files:**
- Create: `src/secondbrain/tracing.py`
- Modify: `tests/test_tracing.py`

- [ ] **Step 1: Write failing tests for FileSpanExporter**

Append to `tests/test_tracing.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock

from opentelemetry.sdk.trace.export import SpanExportResult

from secondbrain.tracing import FileSpanExporter


def test_file_span_exporter_creates_directory(tmp_path):
    traces_dir = tmp_path / "traces"
    exporter = FileSpanExporter(traces_dir)
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
    # Filename should be today's UTC date
    from datetime import datetime, timezone
    expected_name = datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"
    assert files[0].name == expected_name
    # Content should be one line of valid JSON
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
    # Point to a non-writable path
    traces_dir = tmp_path / "traces"
    exporter = FileSpanExporter(traces_dir)

    span = MagicMock()
    span.to_json.side_effect = Exception("serialization error")

    result = exporter.export([span])
    assert result == SpanExportResult.FAILURE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/test_tracing.py -v -k "file_span_exporter"`
Expected: FAIL — `secondbrain.tracing` module does not exist

- [ ] **Step 3: Implement FileSpanExporter**

Create `src/secondbrain/tracing.py`:

```python
"""OTel tracing initialization for eval tooling integration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/test_tracing.py -v -k "file_span_exporter"`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/tracing.py tests/test_tracing.py
git commit -m "feat(tracing): implement FileSpanExporter with JSONL output"
```

---

### Task 4: Implement `init_tracing()`

**Files:**
- Modify: `src/secondbrain/tracing.py`
- Modify: `tests/test_tracing.py`

- [ ] **Step 1: Write failing tests for init_tracing**

Append to `tests/test_tracing.py`:

```python
from unittest.mock import patch

from secondbrain.config import Settings
from secondbrain.tracing import init_tracing


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/test_tracing.py -v -k "init_tracing"`
Expected: FAIL — `init_tracing` not yet defined or `Traceloop` import missing

- [ ] **Step 3: Implement init_tracing**

Add to `src/secondbrain/tracing.py`, after the `FileSpanExporter` class:

```python
def init_tracing(settings: Settings) -> None:
    """Initialize OTel tracing if enabled. Call once at app startup."""
    if not settings.tracing_enabled:
        return

    from traceloop.sdk import Traceloop

    traces_dir = Path(settings.data_path) / "traces"
    exporter = FileSpanExporter(traces_dir)

    Traceloop.init(
        app_name="secondbrain",
        exporter=exporter,
    )

    logger.info("OTel tracing enabled — writing spans to %s", traces_dir)
```

Also remove the `TYPE_CHECKING` guard on the `Settings` import since `init_tracing` uses it at runtime. Update the imports:

```python
from secondbrain.config import Settings
```

Wait — this creates a circular import risk. `config.py` doesn't import from `tracing.py`, so `tracing.py` importing `Settings` from `config.py` is safe. Keep the runtime import.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/test_tracing.py -v -k "init_tracing"`
Expected: Both tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/tracing.py tests/test_tracing.py
git commit -m "feat(tracing): implement init_tracing with Traceloop.init"
```

---

### Task 5: Integrate tracing into FastAPI startup

**Files:**
- Modify: `src/secondbrain/main.py:34-40`

- [ ] **Step 1: Write failing test**

Append to `tests/test_tracing.py`:

```python
def test_main_calls_init_tracing():
    """Verify main.py lifespan calls init_tracing."""
    import ast

    main_path = Path(__file__).parent.parent / "src" / "secondbrain" / "main.py"
    source = main_path.read_text()
    tree = ast.parse(source)

    # Check that init_tracing is imported
    imports = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    tracing_imported = any(
        getattr(node, "module", "") == "secondbrain.tracing"
        for node in imports
    )
    assert tracing_imported, "main.py must import from secondbrain.tracing"

    # Check that init_tracing is called in the source
    assert "init_tracing" in source, "main.py must call init_tracing"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/test_tracing.py::test_main_calls_init_tracing -v`
Expected: FAIL — main.py doesn't import from secondbrain.tracing yet

- [ ] **Step 3: Add init_tracing to main.py lifespan**

In `src/secondbrain/main.py`, add the import after line 26:

```python
from secondbrain.tracing import init_tracing
```

In the `lifespan` function, add `init_tracing(s)` as the first line after `s = get_settings()` (after line 36):

```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Log resolved configuration at startup for debugging."""
    s = get_settings()
    init_tracing(s)
    logger.info("SecondBrain starting — vault_path=%s, data_path=%s", s.vault_path, s.data_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/test_tracing.py::test_main_calls_init_tracing -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/main.py tests/test_tracing.py
git commit -m "feat(tracing): integrate init_tracing into FastAPI lifespan"
```

---

### Task 6: Integrate tracing into daily_sync and inbox_processor

**Files:**
- Modify: `src/secondbrain/scripts/daily_sync.py:167`
- Modify: `src/secondbrain/scripts/inbox_processor.py:230`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tracing.py`:

```python
def test_daily_sync_calls_init_tracing():
    """Verify daily_sync.py calls init_tracing."""
    source_path = Path(__file__).parent.parent / "src" / "secondbrain" / "scripts" / "daily_sync.py"
    source = source_path.read_text()
    assert "init_tracing" in source, "daily_sync.py must call init_tracing"


def test_inbox_processor_calls_init_tracing():
    """Verify inbox_processor.py calls init_tracing."""
    source_path = Path(__file__).parent.parent / "src" / "secondbrain" / "scripts" / "inbox_processor.py"
    source = source_path.read_text()
    assert "init_tracing" in source, "inbox_processor.py must call init_tracing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/test_tracing.py -v -k "daily_sync_calls or inbox_processor_calls"`
Expected: FAIL — neither file contains `init_tracing` yet

- [ ] **Step 3: Add init_tracing to daily_sync.py**

In `src/secondbrain/scripts/daily_sync.py`, add import at the top (after line 14):

```python
from secondbrain.tracing import init_tracing
```

In `main()`, add `init_tracing(settings)` after `settings = get_settings()` (after line 167):

```python
    settings = get_settings()
    init_tracing(settings)
```

- [ ] **Step 4: Add init_tracing to inbox_processor.py**

In `src/secondbrain/scripts/inbox_processor.py`, add import at the top (after line 18):

```python
from secondbrain.tracing import init_tracing
```

In `process_inbox()`, add at the start of the function (after `def process_inbox(vault_path: Path) -> list[str]:`):

```python
def process_inbox(vault_path: Path) -> list[str]:
    settings = get_settings()
    init_tracing(settings)
```

Note: `inbox_processor.py` imports `load_settings` from `secondbrain.settings` (line 19). Check if `get_settings` from `secondbrain.config` is already available or needs importing. If `load_settings` is a different function, use whichever provides a `Settings` object with `tracing_enabled`. Verify by reading the `settings.py` module.

Actually — `inbox_processor.py` uses `load_settings` from `secondbrain.settings`, not `get_settings` from `secondbrain.config`. These may return different types. The safest approach: import `get_settings` from `secondbrain.config` (same as `daily_sync.py`) and use that for `init_tracing`:

```python
from secondbrain.config import get_settings
from secondbrain.tracing import init_tracing
```

Then at the top of `process_inbox()`:

```python
    init_tracing(get_settings())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/test_tracing.py -v -k "daily_sync_calls or inbox_processor_calls"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/secondbrain/scripts/daily_sync.py src/secondbrain/scripts/inbox_processor.py tests/test_tracing.py
git commit -m "feat(tracing): integrate init_tracing into daily_sync and inbox_processor"
```

---

### Task 7: Add mypy overrides for traceloop and opentelemetry

**Files:**
- Modify: `pyproject.toml:78-88`

- [ ] **Step 1: Run mypy to see type errors**

Run: `cd /Users/brentrossin/SecondBrain && python -m mypy src/secondbrain/tracing.py`
Expected: Errors about missing type stubs for `traceloop` and possibly `opentelemetry`

- [ ] **Step 2: Add mypy overrides**

In `pyproject.toml`, add `traceloop` and `traceloop.*` and `opentelemetry.*` to the `ignore_missing_imports` override list (around line 80):

```toml
[[tool.mypy.overrides]]
module = [
    "frontmatter",
    "chromadb.*",
    "sentence_transformers",
    "gradio",
    "gradio.*",
    "anthropic",
    "anthropic.*",
    "traceloop.*",
    "opentelemetry.*",
]
ignore_missing_imports = true
```

- [ ] **Step 3: Run mypy again**

Run: `cd /Users/brentrossin/SecondBrain && python -m mypy src/secondbrain/tracing.py`
Expected: No errors (or only pre-existing errors unrelated to tracing)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add mypy overrides for traceloop and opentelemetry"
```

---

### Task 8: Enable tracing in .env and run full verification

**Files:**
- Modify: `.env`

- [ ] **Step 1: Add tracing env var**

Add to `.env`:

```
SECONDBRAIN_TRACING_ENABLED=true
```

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/brentrossin/SecondBrain && python -m pytest tests/ -v`
Expected: All tests pass, including all new tracing tests. No existing tests broken.

- [ ] **Step 3: Run linter**

Run: `cd /Users/brentrossin/SecondBrain && python -m ruff check src/secondbrain/tracing.py tests/test_tracing.py`
Expected: No errors

- [ ] **Step 4: Run type checker**

Run: `cd /Users/brentrossin/SecondBrain && python -m mypy src/secondbrain/tracing.py`
Expected: No errors

- [ ] **Step 5: Manual smoke test — restart API and make a query**

```bash
# Restart the API server
launchctl unload ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 2 && kill -9 $(lsof -ti:8000) 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 3 && curl -s http://localhost:8000/health
```

Then make a test query:

```bash
curl -s http://localhost:8000/api/v1/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"query": "test trace generation"}' | head -20
```

Check that a trace file was created:

```bash
ls -la data/traces/
cat data/traces/$(date -u +%Y-%m-%d).jsonl | head -5
```

Expected: JSONL file exists with span data containing model name, tokens, input/output values.

- [ ] **Step 6: Commit .env change**

```bash
git add .env
git commit -m "feat(tracing): enable OTel tracing in .env"
```

Note: `.env` is gitignored, so this won't actually commit. The change is local-only. This step is just confirming the file is updated.

---

## Post-Implementation

After all tasks are complete:

1. Run `/tri-review` on all changed files
2. Create PR via `/roadmap review TRACE-1`
3. After merge: `/roadmap deliver TRACE-1`
