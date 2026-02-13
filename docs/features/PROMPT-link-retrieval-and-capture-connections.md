# Implementation Agent Prompt: Link-Aware Retrieval + Capture Connection Surfacing

You are implementing two related features for the SecondBrain project. Read these two feature specs carefully before starting:

1. `docs/features/link-aware-retrieval.md` — 1-hop wiki link following in the RAG pipeline
2. `docs/features/capture-connection-surfacing.md` — show related notes after quick capture

Both features enhance retrieval but are **independent** — neither depends on the other. Implement them in the order below.

---

## Context

- SecondBrain is a FastAPI + Next.js app that indexes an Obsidian vault for hybrid search (BM25 + vectors) and LLM-powered answers
- The vault parser (`src/secondbrain/vault/parser.py`) currently does NOT extract `[[wiki links]]`
- The capture endpoint (`src/secondbrain/api/capture.py`) currently writes to disk and returns a filename — no retrieval
- The answerer (`src/secondbrain/synthesis/answerer.py`) receives context via `_build_context()` from reranked candidates only
- The Insights page (`frontend/src/app/(dashboard)/insights/page.tsx`) is a placeholder — do NOT modify it in this work

---

## Feature 1: Link-Aware Retrieval

Read `docs/features/link-aware-retrieval.md` for the full spec. Implement in this order:

### Step 1: Wiki link parser (`src/secondbrain/vault/links.py`)

Create a new module with a function:

```python
def extract_wiki_links(text: str) -> list[str]:
    """Extract [[wiki link]] targets from markdown text.

    Handles: [[Note]], [[Note|alias]], [[Note#heading]], [[Note#heading|alias]]
    Excludes links inside code blocks (backtick-fenced).
    Returns deduplicated list of target titles.
    """
```

Use regex: `\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]`
Strip code blocks before parsing (both inline `` ` `` and fenced `` ``` ``).

### Step 2: Link resolver on LexicalStore (`src/secondbrain/stores/lexical.py`)

Add a method:

```python
def resolve_note_path(self, title: str) -> str | None:
    """Resolve a wiki link title to a note_path. Case-insensitive."""
```

Query: `SELECT DISTINCT note_path FROM chunks WHERE LOWER(note_title) = LOWER(?) LIMIT 1`

### Step 3: Link expander (`src/secondbrain/retrieval/link_expander.py`)

Create a new module:

```python
@dataclass
class LinkedContext:
    note_path: str
    note_title: str
    chunk_text: str
    linked_from: str  # note_title of the source candidate

class LinkExpander:
    def __init__(self, lexical_store: LexicalStore) -> None: ...

    def expand(
        self,
        ranked_candidates: list[RankedCandidate],
        max_linked: int = 3,
    ) -> list[LinkedContext]: ...
```

Algorithm:
1. Iterate ranked candidates in score order
2. Parse `[[wiki links]]` from each `candidate.chunk_text`
3. Resolve each title → note_path via `lexical_store.resolve_note_path()`
4. Skip if note_path is already in candidates or already collected
5. Fetch first chunk (chunk_index=0) from linked note: `SELECT * FROM chunks WHERE note_path = ? ORDER BY chunk_index LIMIT 1`
6. Stop when `max_linked` reached
7. Return list of `LinkedContext`

### Step 4: Answerer integration (`src/secondbrain/synthesis/answerer.py`)

Modify `answer()` and `answer_stream()` to accept an optional `linked_context: list[LinkedContext] | None = None` parameter.

Modify `_build_context()` to accept linked context and append after main candidates:

```
---

CONNECTED NOTES (linked from retrieved results):

[C1] [note_folder] Note Title (linked from: Source Note Title)
chunk text here...
```

Only append this section if `linked_context` is non-empty.

Add one sentence to `SYSTEM_PROMPT`:
```
8. You also have access to connected notes that are explicitly linked from the retrieved sources. Use them for additional context when relevant.
```

### Step 5: Pipeline wiring (`src/secondbrain/api/ask.py` + `src/secondbrain/api/dependencies.py`)

In `dependencies.py`, add:
```python
def get_link_expander() -> LinkExpander:
    return LinkExpander(get_lexical_store())
```

In `ask.py`, after reranking and before answering (in both `ask()` and `ask_stream()`):
```python
link_expander = get_link_expander()
linked_context = link_expander.expand(ranked_candidates)
```

Pass `linked_context` to `answerer.answer()` and `answerer.answer_stream()`.

**Important:** Do NOT add linked notes to citations. They are supplementary context only.

---

## Feature 2: Capture Connection Surfacing

Read `docs/features/capture-connection-surfacing.md` for the full spec. Implement in this order:

### Step 1: Models (`src/secondbrain/models.py`)

Add:
```python
class CaptureConnection(BaseModel):
    """A note related to captured text."""
    note_path: str
    note_title: str
    snippet: str
    score: float
```

Update `CaptureResponse`:
```python
class CaptureResponse(BaseModel):
    filename: str
    message: str
    connections: list[CaptureConnection] = []
```

### Step 2: Backend capture endpoint (`src/secondbrain/api/capture.py`)

After writing the file, add retrieval:

```python
connections: list[CaptureConnection] = []
try:
    retriever = get_retriever()
    candidates = retriever.retrieve(request.text, top_k=10)

    # Deduplicate by note_path, keep highest RRF score
    seen: dict[str, RetrievalCandidate] = {}
    for c in candidates:
        if c.note_path not in seen or c.rrf_score > seen[c.note_path].rrf_score:
            seen[c.note_path] = c

    top = sorted(seen.values(), key=lambda c: c.rrf_score, reverse=True)[:5]

    # Try to use metadata summaries as snippets
    try:
        metadata_store = get_metadata_store()
        for c in top:
            meta = metadata_store.get(c.note_path)
            snippet = meta.summary if meta and meta.summary else c.chunk_text[:150].strip()
            connections.append(CaptureConnection(
                note_path=c.note_path,
                note_title=c.note_title,
                snippet=snippet,
                score=round(c.rrf_score, 4),
            ))
    except Exception:
        # Metadata unavailable, use chunk text
        connections = [
            CaptureConnection(
                note_path=c.note_path,
                note_title=c.note_title,
                snippet=c.chunk_text[:150].strip(),
                score=round(c.rrf_score, 4),
            )
            for c in top
        ]
except Exception:
    logger.debug("Connection surfacing failed, returning capture without connections")
```

You'll need to import `get_retriever` and `get_metadata_store` from dependencies. Add any missing dependency functions.

**Critical:** Capture must NEVER fail because of retrieval errors. The try/except wrapping the entire retrieval block is mandatory.

### Step 3: Frontend API types (`frontend/src/lib/api.ts`)

Update the capture response type and ensure `captureText()` returns the new shape:

```typescript
interface CaptureConnection {
  note_path: string;
  note_title: string;
  snippet: string;
  score: number;
}

// Update the existing CaptureResponse or add connections to the return
```

### Step 4: Frontend connection cards (`frontend/src/components/capture/CaptureForm.tsx`)

After a successful capture with connections:
- Show a "Related in your vault:" label below the success message
- Map over connections to render compact cards:
  - Folder badge (extract from `note_path` — first segment before `/`)
  - Note title (bold, `text-sm font-medium text-text`)
  - Snippet (truncated, `text-xs text-text-dim`)
- Cards use the existing `glass-card` pattern but more compact (less padding)
- Cards disappear when the user starts typing a new capture (clear connections state when `text` changes from empty to non-empty)
- If connections is empty, render nothing extra

---

## What NOT to do

- Do NOT modify the Insights page
- Do NOT add linked notes to the citation list in /ask responses
- Do NOT add LLM reranking to the capture connections (raw hybrid scores only)
- Do NOT trigger reindexing from the capture endpoint
- Do NOT add multi-hop link traversal (1 hop only)
- Do NOT over-engineer — no new database tables, no new config options, no feature flags

## Commit workflow

After implementing each feature:
1. Write the code
2. Run `/test-generation` to generate tests
3. Run `code-simplifier` agent to review before committing
4. Commit with a descriptive message

Commit each feature separately (two commits total).

## After both features are implemented

Restart the backend server (it must start from project root `/Users/brentrossin/SecondBrain/`):
```bash
cd /Users/brentrossin/SecondBrain
kill -9 $(lsof -ti:8000) 2>/dev/null
export PATH="$HOME/.local/bin:$PATH"
nohup uv run uvicorn secondbrain.main:app --host 127.0.0.1 --port 8000 > /tmp/secondbrain-api.log 2>&1 &
sleep 3 && curl -s http://localhost:8000/health
```

Rebuild and restart the frontend:
```bash
cd /Users/brentrossin/SecondBrain/frontend && npm run build
launchctl unload ~/Library/LaunchAgents/com.secondbrain.ui.plist
sleep 2 && kill -9 $(lsof -ti:7860) 2>/dev/null
launchctl load ~/Library/LaunchAgents/com.secondbrain.ui.plist
sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:7860/
```
