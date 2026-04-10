# RAG-1: Contextual Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM-generated context blurbs to chunks at index time so both vector and BM25 search benefit from document-level context.

**Architecture:** New `ContextGenerator` class in `indexing/context.py` calls Anthropic Haiku per chunk with full document context. Blurbs stored on the `Chunk` model (`context_blurb` field), persisted in both lexical (FTS5) and vector (ChromaDB) stores. `build_embedding_text()` prepends blurb before embedding.

**Tech Stack:** Anthropic SDK (claude-haiku-4-5), SQLite FTS5, ChromaDB, existing UsageStore for cost tracking

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/secondbrain/models.py:48-60` | Add `context_blurb` field to `Chunk` |
| Modify | `src/secondbrain/config.py:59` | Add `context_generation_enabled` setting |
| Create | `src/secondbrain/indexing/context.py` | `ContextGenerator` class |
| Modify | `src/secondbrain/indexing/embedder.py:46-60` | Prepend blurb in `build_embedding_text()` |
| Modify | `src/secondbrain/stores/lexical.py:78-180` | Add `context_blurb` column + FTS5 schema v3 |
| Modify | `src/secondbrain/stores/vector.py:134-142` | Store `context_blurb` in metadata |
| Modify | `src/secondbrain/api/index.py:85-104` | Wire `ContextGenerator` into pipeline |
| Create | `tests/test_context_generator.py` | All tests for this feature |

---

### Task 1: Add `context_blurb` field to Chunk model + config

**Files:**
- Modify: `src/secondbrain/models.py:48-60`
- Modify: `src/secondbrain/config.py:59`
- Create: `tests/test_context_generator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_context_generator.py`:

```python
"""Tests for contextual retrieval — context blurb generation and integration."""

from secondbrain.config import Settings
from secondbrain.models import Chunk


def test_chunk_has_context_blurb_field():
    chunk = Chunk(
        chunk_id="abc123",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Section"],
        chunk_index=0,
        chunk_text="some text",
        checksum="def456",
    )
    assert chunk.context_blurb is None


def test_chunk_accepts_context_blurb():
    chunk = Chunk(
        chunk_id="abc123",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Section"],
        chunk_index=0,
        chunk_text="some text",
        checksum="def456",
        context_blurb="This is context about the test note.",
    )
    assert chunk.context_blurb == "This is context about the test note."


def test_context_generation_enabled_by_default():
    settings = Settings(_env_file=None, vault_path="/tmp/fake")
    assert settings.context_generation_enabled is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py -v`
Expected: FAIL — `Chunk` has no `context_blurb` field

- [ ] **Step 3: Add fields**

In `src/secondbrain/models.py`, add after `note_date` (line 60):
```python
    context_blurb: str | None = None
```

In `src/secondbrain/config.py`, add after `tracing_enabled` (line 61):
```python
    # Contextual retrieval
    context_generation_enabled: bool = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/models.py src/secondbrain/config.py tests/test_context_generator.py
git commit -m "feat(rag): add context_blurb field to Chunk model + config"
```

---

### Task 2: Update `build_embedding_text()` to prepend blurb

**Files:**
- Modify: `src/secondbrain/indexing/embedder.py:46-60`
- Modify: `tests/test_context_generator.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_context_generator.py`:

```python
from secondbrain.indexing.embedder import build_embedding_text


def test_build_embedding_text_with_blurb():
    chunk = Chunk(
        chunk_id="abc123",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Recipes", "Dinner"],
        chunk_index=0,
        chunk_text="3 medium parsnips, peeled",
        checksum="def456",
        context_blurb="Ingredients for Parsnip Purée from a Valentine's Day dinner recipe.",
    )
    result = build_embedding_text(chunk)
    assert result.startswith("[Context: Ingredients for Parsnip Purée")
    assert "Recipes > Dinner" in result
    assert "3 medium parsnips, peeled" in result


def test_build_embedding_text_without_blurb():
    chunk = Chunk(
        chunk_id="abc123",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Recipes"],
        chunk_index=0,
        chunk_text="some text",
        checksum="def456",
    )
    result = build_embedding_text(chunk)
    assert not result.startswith("[Context:")
    assert result == "Recipes\nsome text"
```

- [ ] **Step 2: Run tests to verify the blurb test fails**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py::test_build_embedding_text_with_blurb -v`
Expected: FAIL — blurb not prepended

- [ ] **Step 3: Update `build_embedding_text()`**

In `src/secondbrain/indexing/embedder.py`, replace `build_embedding_text` (lines 46-60):

```python
def build_embedding_text(chunk: "Chunk") -> str:
    """Build text for embedding by prepending context blurb and heading path.

    Produces text like:
        [Context: Ingredients for Parsnip Purée, part of a Valentine's Day dinner.]
        Recipes > Valentine's Day Dinner > Parsnip Purée
        3 medium parsnips, peeled and chopped
    """
    parts: list[str] = []
    if chunk.context_blurb:
        parts.append(f"[Context: {chunk.context_blurb}]")
    if chunk.heading_path:
        parts.append(" > ".join(chunk.heading_path))
    parts.append(chunk.chunk_text)
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/indexing/embedder.py tests/test_context_generator.py
git commit -m "feat(rag): prepend context blurb in build_embedding_text"
```

---

### Task 3: Implement `ContextGenerator`

**Files:**
- Create: `src/secondbrain/indexing/context.py`
- Modify: `tests/test_context_generator.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_context_generator.py`:

```python
import uuid
from unittest.mock import MagicMock, patch

from secondbrain.indexing.context import ContextGenerator


def _make_chunk(text: str, heading: str = "Section") -> Chunk:
    return Chunk(
        chunk_id="test123",
        note_path="10_Notes/Test.md",
        note_title="Test Note",
        heading_path=[heading],
        chunk_index=0,
        chunk_text=text,
        checksum="check123",
    )


def test_context_generator_returns_blurbs(tmp_path):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="This chunk describes testing patterns.")]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 20

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("secondbrain.indexing.context.Anthropic", return_value=mock_client):
        gen = ContextGenerator(api_key="test-key")
        chunks = [_make_chunk("def test_foo(): pass")]
        blurbs = gen.generate_blurbs("Test Note", "# Test\ndef test_foo(): pass", chunks)

    assert len(blurbs) == 1
    assert blurbs[0] == "This chunk describes testing patterns."
    mock_client.messages.create.assert_called_once()


def test_context_generator_handles_api_error(tmp_path):
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    with patch("secondbrain.indexing.context.Anthropic", return_value=mock_client):
        gen = ContextGenerator(api_key="test-key")
        chunks = [_make_chunk("some text")]
        blurbs = gen.generate_blurbs("Test", "# Test\nsome text", chunks)

    assert len(blurbs) == 1
    assert blurbs[0] == ""


def test_context_generator_multiple_chunks():
    responses = []
    for i in range(3):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=f"Context for chunk {i}.")]
        mock_resp.usage.input_tokens = 100
        mock_resp.usage.output_tokens = 20
        responses.append(mock_resp)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = responses

    with patch("secondbrain.indexing.context.Anthropic", return_value=mock_client):
        gen = ContextGenerator(api_key="test-key")
        chunks = [_make_chunk(f"chunk {i}") for i in range(3)]
        blurbs = gen.generate_blurbs("Note", "full doc", chunks)

    assert len(blurbs) == 3
    assert blurbs[1] == "Context for chunk 1."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py -v -k "context_generator"`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement ContextGenerator**

Create `src/secondbrain/indexing/context.py`:

```python
"""LLM-powered context blurb generation for contextual retrieval."""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from anthropic import Anthropic

if TYPE_CHECKING:
    from secondbrain.models import Chunk
    from secondbrain.stores.usage import UsageStore

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a context annotation assistant for a personal knowledge base. \
Given a document and a specific chunk from it, write a short (1-2 sentence) context blurb \
that situates this chunk within the document. Include the document topic, relevant section \
context, and any key entities that aren't in the chunk itself. Be concise and factual."""

_USER_TEMPLATE = """<document title="{title}">
{document}
</document>

<chunk>
{chunk}
</chunk>

Write a 1-2 sentence context blurb for this chunk."""


class ContextGenerator:
    """Generates context blurbs for chunks using Anthropic Haiku."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5",
        usage_store: UsageStore | None = None,
    ) -> None:
        self._client = Anthropic(api_key=api_key, timeout=60.0)
        self._model = model
        self._usage_store = usage_store

    def generate_blurbs(
        self,
        note_title: str,
        note_content: str,
        chunks: list[Chunk],
        trace_id: str | None = None,
    ) -> list[str]:
        """Generate context blurbs for a list of chunks.

        Returns a list of blurb strings aligned 1:1 with input chunks.
        On error for any chunk, returns empty string for that chunk.
        """
        if trace_id is None:
            trace_id = uuid.uuid4().hex

        blurbs: list[str] = []
        for chunk in chunks:
            blurb = self._generate_one(note_title, note_content, chunk, trace_id)
            blurbs.append(blurb)
        return blurbs

    def _generate_one(
        self,
        note_title: str,
        note_content: str,
        chunk: Chunk,
        trace_id: str,
    ) -> str:
        """Generate a single context blurb for one chunk."""
        start = time.time()
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=150,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": _USER_TEMPLATE.format(
                            title=note_title,
                            document=note_content,
                            chunk=chunk.chunk_text,
                        ),
                    }
                ],
            )
            blurb = response.content[0].text.strip()
            latency_ms = (time.time() - start) * 1000

            if self._usage_store:
                self._usage_store.log_usage(
                    provider="anthropic",
                    model=self._model,
                    usage_type="context_generation",
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    trace_id=trace_id,
                    latency_ms=latency_ms,
                    status="ok",
                )

            return blurb

        except Exception:
            latency_ms = (time.time() - start) * 1000
            logger.warning(
                "Failed to generate context blurb for chunk %s",
                chunk.chunk_id,
                exc_info=True,
            )

            if self._usage_store:
                self._usage_store.log_usage(
                    provider="anthropic",
                    model=self._model,
                    usage_type="context_generation",
                    input_tokens=0,
                    output_tokens=0,
                    trace_id=trace_id,
                    latency_ms=latency_ms,
                    status="error",
                )

            return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py -v -k "context_generator"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/indexing/context.py tests/test_context_generator.py
git commit -m "feat(rag): implement ContextGenerator with Anthropic Haiku"
```

---

### Task 4: Update lexical store schema for `context_blurb`

**Files:**
- Modify: `src/secondbrain/stores/lexical.py`
- Modify: `tests/test_context_generator.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_context_generator.py`:

```python
from secondbrain.stores.lexical import LexicalStore


def test_lexical_store_stores_context_blurb(tmp_path):
    store = LexicalStore(tmp_path / "test.db")
    chunk = Chunk(
        chunk_id="blurb_test_1",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Section"],
        chunk_index=0,
        chunk_text="some text",
        checksum="abc",
        context_blurb="This chunk is about testing.",
    )
    store.add_chunks([chunk])
    result = store.get_chunk("blurb_test_1")
    assert result is not None
    assert result["context_blurb"] == "This chunk is about testing."


def test_lexical_store_blurb_in_fts_search(tmp_path):
    store = LexicalStore(tmp_path / "test.db")
    chunk = Chunk(
        chunk_id="fts_blurb_1",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Section"],
        chunk_index=0,
        chunk_text="3 medium parsnips peeled",
        checksum="abc",
        context_blurb="Ingredients for Valentine dinner recipe",
    )
    store.add_chunks([chunk])
    # Search for a term only in the blurb, not the chunk text
    results = store.search("Valentine")
    assert len(results) >= 1
    assert results[0][0] == "fts_blurb_1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py -v -k "lexical_store"`
Expected: FAIL — `context_blurb` column doesn't exist

- [ ] **Step 3: Update lexical store**

In `src/secondbrain/stores/lexical.py`:

**a)** Bump FTS schema version (line 78):
```python
_FTS_SCHEMA_VERSION = 3  # v3: added context_blurb column
```

**b)** Add `context_blurb` column to the `_migrate_chunk_columns` method (after line 132):
```python
if "context_blurb" not in columns:
    self.conn.execute("ALTER TABLE chunks ADD COLUMN context_blurb TEXT")
```

**c)** Update the FTS5 virtual table definition in `_ensure_fts_schema` — both the versioned recreation (line 152-159) and the fallback CREATE (line 170-178) to include `context_blurb`:
```sql
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    chunk_id,
    note_title,
    heading_path,
    chunk_text,
    context_blurb,
    content='chunks',
    content_rowid='rowid'
)
```

**d)** Update `add_chunks` (lines 190-210) to include `context_blurb` in the INSERT:
```python
rows = [
    (
        c.chunk_id,
        c.note_path,
        c.note_title,
        "|".join(c.heading_path),
        c.chunk_index,
        c.chunk_text,
        c.checksum,
        c.note_folder or "",
        c.note_date,
        c.context_blurb or "",
    )
    for c in chunks
]

sql = """
    INSERT OR REPLACE INTO chunks
    (chunk_id, note_path, note_title, heading_path, chunk_index,
     chunk_text, checksum, note_folder, note_date, context_blurb)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py -v -k "lexical_store"`
Expected: PASS

- [ ] **Step 5: Run existing lexical tests to verify no regressions**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_stores.py -v`
Expected: All existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/secondbrain/stores/lexical.py tests/test_context_generator.py
git commit -m "feat(rag): add context_blurb to lexical store schema + FTS5 v3"
```

---

### Task 5: Update vector store to include `context_blurb` in metadata

**Files:**
- Modify: `src/secondbrain/stores/vector.py:134-142`
- Modify: `tests/test_context_generator.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_context_generator.py`:

```python
def test_vector_store_metadata_includes_blurb(tmp_path):
    """Verify that vector store add_chunks passes context_blurb in metadata."""
    from unittest.mock import MagicMock, patch

    import numpy as np

    from secondbrain.stores.vector import VectorStore

    store = VectorStore(str(tmp_path / "chroma"))
    chunk = Chunk(
        chunk_id="vec_blurb_1",
        note_path="10_Notes/Test.md",
        note_title="Test",
        heading_path=["Section"],
        chunk_index=0,
        chunk_text="some text",
        checksum="abc",
        context_blurb="Context about testing.",
    )
    embeddings = np.random.rand(1, 384).astype(np.float32)
    store.add_chunks([chunk], embeddings)

    # Retrieve and check metadata
    results = store._collection.get(ids=["vec_blurb_1"], include=["metadatas"])
    assert results["metadatas"][0]["context_blurb"] == "Context about testing."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py::test_vector_store_metadata_includes_blurb -v`
Expected: FAIL — `context_blurb` not in metadata

- [ ] **Step 3: Update vector store**

In `src/secondbrain/stores/vector.py`, find the `add_chunks` method's metadata dict construction (around line 134-142). Add `context_blurb` after `note_date`:

```python
metadatas: list[Metadata] = [
    {
        "note_path": c.note_path,
        "note_title": c.note_title,
        "heading_path": "|".join(c.heading_path),
        "chunk_index": c.chunk_index,
        "checksum": c.checksum,
        "note_folder": c.note_folder or "",
        "note_date": c.note_date or "",
        "context_blurb": c.context_blurb or "",
    }
    for c in chunks
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py::test_vector_store_metadata_includes_blurb -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/secondbrain/stores/vector.py tests/test_context_generator.py
git commit -m "feat(rag): include context_blurb in vector store metadata"
```

---

### Task 6: Wire ContextGenerator into the indexing pipeline

**Files:**
- Modify: `src/secondbrain/api/index.py:47-117`
- Modify: `src/secondbrain/api/dependencies.py` (if dependency injection pattern used)
- Modify: `tests/test_context_generator.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_context_generator.py`:

```python
def test_indexing_pipeline_calls_context_generator():
    """Verify index.py source code wires ContextGenerator into the pipeline."""
    from pathlib import Path

    source_path = Path(__file__).parent.parent / "src" / "secondbrain" / "api" / "index.py"
    source = source_path.read_text()
    assert "ContextGenerator" in source, "index.py must use ContextGenerator"
    assert "generate_blurbs" in source, "index.py must call generate_blurbs"
    assert "context_blurb" in source, "index.py must set context_blurb on chunks"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py::test_indexing_pipeline_calls_context_generator -v`
Expected: FAIL

- [ ] **Step 3: Wire ContextGenerator into `_run_indexing`**

In `src/secondbrain/api/index.py`:

**a)** Add imports at the top:
```python
from secondbrain.indexing.context import ContextGenerator
from secondbrain.stores.usage import UsageStore
```

**b)** Update `_run_indexing` signature to accept optional context generator:
```python
def _run_indexing(
    vault_path: Path,
    vector_store: VectorStore,
    lexical_store: LexicalStore,
    embedder: Embedder,
    tracker: IndexTracker,
    full_rebuild: bool,
    context_generator: ContextGenerator | None = None,
) -> IndexResponse:
```

**c)** In the file indexing loop (after `chunks = chunker.chunk_note(note)` at line 91, after the note_folder/note_date assignment), add context generation:
```python
            # Generate context blurbs if enabled
            if context_generator and chunks:
                blurbs = context_generator.generate_blurbs(
                    note.title, note.content, chunks
                )
                for c, blurb in zip(chunks, blurbs):
                    c.context_blurb = blurb
```

**d)** Update `index_vault` endpoint to create and pass ContextGenerator:
```python
@router.post("/index", response_model=IndexResponse)
async def index_vault(
    settings: Annotated[Settings, Depends(get_settings)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    lexical_store: Annotated[LexicalStore, Depends(get_lexical_store)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    tracker: Annotated[IndexTracker, Depends(get_index_tracker)],
    full_rebuild: bool = False,
) -> IndexResponse:
    # ... existing vault_path validation ...

    # Create context generator if enabled and API key available
    context_generator: ContextGenerator | None = None
    if settings.context_generation_enabled and settings.anthropic_api_key:
        from secondbrain.stores.usage import UsageStore

        data_path = Path(settings.data_path)
        usage_store = UsageStore(data_path / "usage.db")
        context_generator = ContextGenerator(
            api_key=settings.anthropic_api_key,
            usage_store=usage_store,
        )

    return await asyncio.to_thread(
        _run_indexing,
        vault_path,
        vector_store,
        lexical_store,
        embedder,
        tracker,
        full_rebuild,
        context_generator,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/test_context_generator.py::test_indexing_pipeline_calls_context_generator -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/secondbrain/api/index.py tests/test_context_generator.py
git commit -m "feat(rag): wire ContextGenerator into indexing pipeline"
```

---

### Task 7: Lint, typecheck, and full verification

- [ ] **Step 1: Run linter on all changed files**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m ruff check src/secondbrain/indexing/context.py src/secondbrain/indexing/embedder.py src/secondbrain/stores/lexical.py src/secondbrain/stores/vector.py src/secondbrain/api/index.py tests/test_context_generator.py`
Expected: All checks passed

- [ ] **Step 2: Run formatter**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m ruff format src/secondbrain/indexing/context.py tests/test_context_generator.py`

- [ ] **Step 3: Run mypy**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m mypy src/secondbrain/indexing/context.py`

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/brentrossin/SecondBrain && ~/.local/bin/uv run python -m pytest tests/ -v`
Expected: All tests pass, no regressions

- [ ] **Step 5: Smoke test — trigger reindex and verify blurbs**

```bash
# Restart the API server
launchctl unload ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 2 && kill -9 $(lsof -ti:8000) 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.secondbrain.api.plist
sleep 3 && curl -s http://localhost:8000/health

# Trigger a full rebuild to generate blurbs
curl -s 'http://localhost:8000/api/v1/index?full_rebuild=true' -X POST | python3 -m json.tool

# Verify blurbs exist in the admin traces (should see context_generation usage_type)
curl -s 'http://localhost:8000/api/v1/admin/traces?limit=5' | python3 -m json.tool
```

- [ ] **Step 6: Commit any final fixes**

```bash
git add -A
git commit -m "chore(rag): lint, format, and verification fixes"
```

---

## Post-Implementation

After all tasks are complete:

1. Run `/tri-review` on all changed files
2. Create PR via `/roadmap review RAG-1`
3. After merge: `/roadmap deliver RAG-1`
