"""Recall endpoint: ranked, cited Witt notes for "have I solved this before?" (spec 001).

Retrieval only: hybrid BM25 + vector search over ``Witt/`` notes, with no rerank, no
synthesis and no conversation, query-log or usage writes. The calling agent judges
relevance; a fixed sanity floor only removes obvious junk. Every served recall
(200 or 503) appends one line to ``data/recall_log.jsonl``.
"""

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from opentelemetry.instrumentation.utils import suppress_instrumentation

from secondbrain.api.dependencies import (
    get_embedder,
    get_lexical_store,
    get_settings,
    get_vector_store,
)
from secondbrain.config import Settings
from secondbrain.indexing.embedder import Embedder
from secondbrain.models import RecallFilters, RecallHit, RecallKind, RecallRequest, RecallResponse
from secondbrain.retrieval.hybrid import HybridRetriever, RetrievalCandidate
from secondbrain.stores.lexical import LexicalStore
from secondbrain.stores.vector import VectorStore
from secondbrain.vault.witt import WITT_FOLDER, classify_witt_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["recall"])

K_LEX = 50
RRF_K = 60
K_VEC_MIN = 30
K_VEC_MAX = 500
SNIPPET_MAX = 600
RECALL_LOG_NAME = "recall_log.jsonl"

NOT_LOCAL_DETAIL = "recall unavailable: requires the local embedder"
NOTICE_NO_WITT = "no Witt notes indexed yet"
NOTICE_SATURATED = "candidate window saturated; results may be incomplete"
NOTICE_VAULT_MISSING = "vault path missing or not configured; project slug not verified"

_WITT_PREFIX = f"{WITT_FOLDER}/"
_LEARNINGS_PREFIX = f"{WITT_FOLDER}/Learnings/"
_LOG_LOCK = threading.Lock()


def k_vec_for(witt_chunk_count: int) -> int:
    """Vector window: every Witt chunk, at least 30, at most 500 (Decision 6)."""
    return min(max(K_VEC_MIN, witt_chunk_count), K_VEC_MAX)


def make_snippet(text: str) -> str:
    """Cut text to <=600 chars at the last whitespace at or before index 600."""
    if len(text) <= SNIPPET_MAX:
        return text
    for i in range(SNIPPET_MAX, 0, -1):
        if text[i].isspace():
            return text[:i]
    return text[:SNIPPET_MAX]


def _request_id(header: str | None) -> str:
    """The client's X-Request-ID if it is a valid UUID, else a fresh one."""
    if header:
        try:
            return str(uuid.UUID(header))  # canonical form, whatever spelling was sent
        except ValueError:
            pass
    return str(uuid.uuid4())


def _check_project(project: str, vault_path: Path | None) -> tuple[str | None, str | None]:
    """Return (warning, notice) for a project slug, checked against Witt/Projects/ dirs."""
    if vault_path is None or not vault_path.is_dir():
        return None, NOTICE_VAULT_MISSING
    projects_dir = vault_path / WITT_FOLDER / "Projects"
    known: list[str] = []
    if projects_dir.is_dir():
        known = sorted(p.name for p in projects_dir.iterdir() if p.is_dir())
    if project in known:
        return None, None
    return f"unknown project '{project}'; known: {', '.join(known) or 'none'}", None


def _passes_filters(filters: RecallFilters, note_path: str, kind: RecallKind) -> bool:
    """All filters must pass (AND). A project filter also admits cross-project learnings."""
    if filters.project is not None:
        project_prefix = f"{WITT_FOLDER}/Projects/{filters.project}/"
        if not note_path.startswith((project_prefix, _LEARNINGS_PREFIX)):
            return False
    if filters.kinds is not None and kind not in filters.kinds:
        return False
    return note_path not in (filters.exclude_paths or [])


class _VectorLedReader(LexicalStore):
    """Recall's private, per-request, read-only reader of lexical.db (specs 001 and 004).

    The cached LexicalStore shares one check_same_thread=False connection, and concurrent
    recalls on it fail with sqlite3.InterfaceError. Each recall therefore opens its own
    ``mode=ro`` connection: no schema init, no writes, and the shared store /ask depends
    on is left alone. A request uses it from one worker thread at a time, then closes it.

    WARNING: ``get_chunk`` deliberately returns None for every id (ADR-005). Recall drops
    keyword-only candidates anyway, and HybridRetriever only calls ``get_chunk`` for ids
    missing from the vector results, so this skips one wasted query per lexical-only id and
    counts it in ``lexical_only_skipped``. Any other caller would see "chunk not found"
    everywhere: never hand this store to anything but recall's own retriever, never cache
    it and never return it.

    A lexical-only id from a store that ignores ``include_folders`` is counted here, as
    keyword-only, rather than in ``dropped_out_of_scope``. That's harmless.
    """

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self.lexical_only_skipped = 0

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA busy_timeout=5000")
        return self._conn

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:  # noqa: ARG002
        """Count a lexical-only candidate and return None, without running a query."""
        self.lexical_only_skipped += 1
        return None


def _retrieve(retriever: HybridRetriever, query: str, top_k: int) -> list[RetrievalCandidate]:
    """Run retrieval in a worker thread with OTel instrumentation suppressed (no spans)."""
    with suppress_instrumentation():
        return retriever.retrieve(query, top_k=top_k, include_folders=[WITT_FOLDER])


@dataclass
class _RecallState:
    """What the worker call learned, kept even when it fails (spec 004 Decision 2)."""

    witt_chunk_count: int = 0
    lexical_only_skipped: int = 0


def _recall_work(
    db_path: Path,
    build_retriever: Callable[[LexicalStore, int], HybridRetriever],
    query: str,
    holder: _RecallState,
) -> list[RetrievalCandidate]:
    """Open, use and close the private reader on one worker thread (Decision 7 steps 4-5).

    Writes the Witt chunk count into holder before retrieving, so a failure after counting
    still logs the real count and window. Raises whatever counting or retrieval raises.
    """
    # Before the first index run there is no lexical.db, and mode=ro can't create it.
    if not db_path.exists():
        return []
    reader = _VectorLedReader(db_path)
    try:
        holder.witt_chunk_count = reader.count_chunks([WITT_FOLDER])
        if holder.witt_chunk_count == 0:
            return []
        k_vec = k_vec_for(holder.witt_chunk_count)
        return _retrieve(build_retriever(reader, k_vec), query, k_vec + K_LEX)
    finally:
        holder.lexical_only_skipped = reader.lexical_only_skipped
        reader.close()


class _Ranked:
    """Post-retrieval result: one best chunk per note, plus drop counters."""

    def __init__(self) -> None:
        self.best: dict[str, tuple[RetrievalCandidate, RecallKind, str | None]] = {}
        self.dropped_keyword_only = 0
        self.dropped_out_of_scope = 0


def _rank(candidates: list[RetrievalCandidate], filters: RecallFilters) -> _Ranked:
    """Decision 7 steps 6-9: drop keyword-only and out-of-scope, classify, filter, dedupe."""
    ranked = _Ranked()
    for c in candidates:
        if c.similarity_score == 0.0:
            ranked.dropped_keyword_only += 1
            continue
        if not c.note_path.startswith(_WITT_PREFIX):
            logger.warning("recall: dropped out-of-scope candidate %r", c.note_path)
            ranked.dropped_out_of_scope += 1
            continue
        kind, project = classify_witt_path(c.note_path)
        if not _passes_filters(filters, c.note_path, kind):
            continue
        current = ranked.best.get(c.note_path)
        # Ties on RRF go to the lower chunk_id, so the snippet doesn't depend on set order.
        if current is None or (-c.rrf_score, c.chunk_id) < (
            -current[0].rrf_score,
            current[0].chunk_id,
        ):
            ranked.best[c.note_path] = (c, kind, project)
    return ranked


def _append_log(log_path: Path, line: dict[str, Any]) -> None:
    """Append one JSON line. A failure logs a WARNING and never reaches the response.

    A new file is created 0600 (it holds query text); an existing file keeps its mode.
    """
    try:
        text = json.dumps(line) + "\n"
        with _LOG_LOCK:
            fd = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                f = os.fdopen(fd, "a", encoding="utf-8")
            except BaseException:
                os.close(fd)
                raise
            with f:
                f.write(text)
    except (OSError, TypeError, ValueError):
        logger.warning("recall_log write failed: %s", log_path, exc_info=True)


def _log_hit(c: RetrievalCandidate) -> dict[str, Any]:
    return {
        "note_path": c.note_path,
        "chunk_id": c.chunk_id,
        "score": c.rrf_score,
        "similarity": c.similarity_score,
        "bm25": c.bm25_score,
        "text_sha1": hashlib.sha1(c.chunk_text.encode()).hexdigest(),
    }


@router.post("/recall", response_model=RecallResponse)
async def recall(
    request: RecallRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    lexical_store: Annotated[LexicalStore, Depends(get_lexical_store)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    x_request_id: Annotated[str | None, Header()] = None,
) -> RecallResponse:
    """Decision 7 pipeline. 422 on an invalid request (no log line).

    503 {"detail": "recall unavailable: <ExceptionType>"} on any exception in steps 3-11
    (spec 004), or "recall unavailable: requires the local embedder". The traceback is
    logged server-side only; the body contains neither the exception message nor a path.
    A cancelled request writes no log line: CancelledError is not an Exception.
    """
    started = time.perf_counter()
    request_id = _request_id(x_request_id)
    filters = request.filters
    warnings: list[str] = []
    notices: list[str] = []
    holder = _RecallState()
    hits: list[RecallHit] = []
    log_hits: list[dict[str, Any]] = []
    ranked = _Ranked()
    log_path = Path(settings.data_path) / RECALL_LOG_NAME

    async def write_log(status: int, error_type: str | None, latency_ms: int) -> None:
        line = {
            "ts": datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "status": status,
            "error_type": error_type,
            "query": request.query,
            "filters": filters.model_dump(),
            "limit": request.limit,
            "recall_min_similarity": settings.recall_min_similarity,
            "k_vec": k_vec_for(holder.witt_chunk_count),
            "k_lex": K_LEX,
            "rrf_k": RRF_K,
            "witt_chunk_count": holder.witt_chunk_count,
            "hits": log_hits,
            "dropped_keyword_only": holder.lexical_only_skipped + ranked.dropped_keyword_only,
            "dropped_out_of_scope": ranked.dropped_out_of_scope,
            "warnings": warnings,
            "notices": notices,
            "latency_ms": latency_ms,
            "embedding_model": embedder.model_name,
        }
        await asyncio.to_thread(_append_log, log_path, line)

    def elapsed_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    def build_retriever(reader: LexicalStore, k_vec: int) -> HybridRetriever:
        # Looked up at call time, so tests can patch recall_module.HybridRetriever.
        return HybridRetriever(
            vector_store,
            reader,
            embedder,
            k_vec=k_vec,
            k_lex=K_LEX,
            rrf_k=RRF_K,
            min_similarity=settings.recall_min_similarity,
        )

    # Step 2: local embedder only.
    if settings.embedding_provider != "local":
        await write_log(503, "EmbedderNotLocal", elapsed_ms())
        raise HTTPException(status_code=503, detail=NOT_LOCAL_DETAIL)

    try:
        # Step 3: project slug check (filesystem, so off the event loop).
        if filters.project is not None:
            warning, notice = await asyncio.to_thread(
                _check_project, filters.project, settings.vault_path
            )
            if notice:
                notices.append(notice)
            if warning:
                warnings.append(warning)

        if not warnings:
            # Steps 4-5: count Witt chunks, size the window, retrieve (one embedding, no spans).
            candidates = await asyncio.to_thread(
                _recall_work, lexical_store.db_path, build_retriever, request.query, holder
            )
            if holder.witt_chunk_count == 0:
                notices.append(NOTICE_NO_WITT)
            elif holder.witt_chunk_count > K_VEC_MAX:
                notices.append(NOTICE_SATURATED)

            # Steps 6-11: drop, classify, filter, dedupe, sort, slice.
            ranked = _rank(candidates, filters)
            best = sorted(ranked.best.values(), key=lambda t: (-t[0].rrf_score, t[0].note_path))
            best = best[: request.limit]
            hits = [
                RecallHit(
                    note_path=c.note_path,
                    note_title=c.note_title,
                    heading_path=c.heading_path,
                    kind=kind,
                    project=project,
                    snippet=make_snippet(c.chunk_text),
                    score=c.rrf_score,
                    similarity=c.similarity_score,
                )
                for c, kind, project in best
            ]
            log_hits = [_log_hit(c) for c, _kind, _project in best]
    except Exception as exc:
        error_type = type(exc).__name__
        logger.exception("recall failed (request_id=%s): %s", request_id, error_type)
        await write_log(503, error_type, elapsed_ms())
        raise HTTPException(status_code=503, detail=f"recall unavailable: {error_type}") from None

    response = RecallResponse(
        request_id=request_id,
        query=request.query,
        applied_filters=filters,
        hits=hits,
        warnings=warnings,
        notices=notices,
        latency_ms=elapsed_ms(),
        witt_chunk_count=holder.witt_chunk_count,
    )
    await write_log(200, None, response.latency_ms)
    return response
