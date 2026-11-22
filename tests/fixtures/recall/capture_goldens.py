"""Capture golden outputs of today's retrieval calls (spec 001 step 1.5, spec 004 step 1.3).

Run on unchanged code, before any src/ change:

    uv run python -m tests.fixtures.recall.capture_goldens

It builds the fixture index (and spec 004's LEXONLY index) into a temp dir with the stub
embedder and writes `goldens.json` and `recall_goldens.json` next to this file.
`test_existing_callers_unaffected` and `test_recall_endpoint_hits_match_goldens` recompute
the same structures on the changed code and compare.
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain.api import dependencies as deps
from secondbrain.api.recall import router
from secondbrain.config import Settings
from secondbrain.retrieval.hybrid import HybridRetriever
from tests.fixtures.recall.index import (
    FIXTURE_VAULT,
    GOLDENS_PATH,
    LEXONLY_QUERY,
    TEST_QUERY,
    RecallIndex,
    build_index,
    build_lexonly_index,
)

GOLDEN_QUERIES = [TEST_QUERY, "single owner stores", "harness"]
RECALL_GOLDENS_PATH = GOLDENS_PATH.with_name("recall_goldens.json")

# Per query: the unfiltered request plus one per filter kind (spec 004 golden scenario).
RECALL_VARIANTS: dict[str, dict[str, dict[str, Any]]] = {
    TEST_QUERY: {
        "unfiltered": {},
        "project": {"project": "witt"},
        "kinds": {"kinds": ["decision", "spec"]},
        "exclude_paths": {"exclude_paths": ["Witt/Projects/witt/decisions/ADR-001-overrides.md"]},
    },
    LEXONLY_QUERY: {
        "unfiltered": {},
        "project": {"project": "witt"},
        "kinds": {"kinds": ["spec"]},
        "exclude_paths": {"exclude_paths": ["Witt/Projects/witt/decisions/ADR-010-lex.md"]},
    },
}


def _round5(x: float) -> float:
    return round(float(x), 5)


def trace_lexical_sql(conn: sqlite3.Connection) -> list[str]:
    """Attach a trace callback to conn and return the list it appends statements to."""
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    return statements


def compute_goldens(idx: RecallIndex) -> dict[str, Any]:
    """Today's retrieve / VectorStore.search / LexicalStore.search outputs, plus lexical SQL."""
    retriever = HybridRetriever(idx.vector_store, idx.lexical_store, idx.embedder)
    out: dict[str, Any] = {
        "retrieve": {},
        "vector_search": {},
        "lexical_search": {},
        "lexical_sql": {},
    }
    for q in GOLDEN_QUERIES:
        # RRF ties come out of a set in arbitrary order, so ties are sorted by chunk_id.
        retrieved = sorted(
            retriever.retrieve(q, top_k=10), key=lambda c: (-_round5(c.rrf_score), c.chunk_id)
        )
        out["retrieve"][q] = [
            {
                "chunk_id": c.chunk_id,
                "note_path": c.note_path,
                "note_title": c.note_title,
                "heading_path": c.heading_path,
                "similarity": _round5(c.similarity_score),
                "bm25": _round5(c.bm25_score),
                "rrf": _round5(c.rrf_score),
                "note_folder": c.note_folder,
            }
            for c in retrieved
        ]
        emb = idx.embedder.embed_single(q)
        out["vector_search"][q] = [
            {"chunk_id": cid, "similarity": _round5(sim), "note_path": meta.get("note_path")}
            for cid, sim, meta, _doc in idx.vector_store.search(emb, top_k=30)
        ]
        statements = trace_lexical_sql(idx.lexical_store.conn)
        try:
            out["lexical_search"][q] = [
                [cid, _round5(score)] for cid, score in idx.lexical_store.search(q, top_k=50)
            ]
        finally:
            idx.lexical_store.conn.set_trace_callback(None)
        # Keep top-level statements; FTS5's own internal queries start with "--".
        out["lexical_sql"][q] = [s for s in statements if not s.lstrip().startswith("--")]
    return out


def _recall_hits(idx: RecallIndex, data_path: Path, query: str, filters: dict[str, Any]) -> list:
    """POST /api/v1/recall over idx; hits as [note_path, chunk_id, round5 score, round5 sim]."""
    data_path.mkdir(parents=True, exist_ok=True)
    settings = Settings(_env_file=None, vault_path=idx.vault_path, data_path=data_path)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides = {
        deps.get_settings: lambda: settings,
        deps.get_vector_store: lambda: idx.vector_store,
        deps.get_lexical_store: lambda: idx.lexical_store,
        deps.get_embedder: lambda: idx.embedder,
    }
    resp = TestClient(app).post(
        "/api/v1/recall", json={"query": query, "filters": filters, "limit": 20}
    )
    resp.raise_for_status()
    hits = [
        [h["note_path"], h["chunk_id"], _round5(h["score"]), _round5(h["similarity"])]
        for h in _hits_with_chunk_ids(resp.json()["hits"], data_path)
    ]
    return sorted(hits, key=lambda h: (-h[2], h[0]))


def _hits_with_chunk_ids(hits: list[dict[str, Any]], data_path: Path) -> list[dict[str, Any]]:
    """Join response hits with the chunk ids the recall log recorded for the same request."""
    log_lines = (data_path / "recall_log.jsonl").read_text(encoding="utf-8").splitlines()
    chunk_ids = {h["note_path"]: h["chunk_id"] for h in json.loads(log_lines[-1])["hits"]}
    return [h | {"chunk_id": chunk_ids[h["note_path"]]} for h in hits]


def compute_recall_goldens(
    fixture: RecallIndex, lexonly: RecallIndex, data_path: Path
) -> dict[str, Any]:
    """Recall endpoint hits for TEST_QUERY (fixture) and LEXONLY_QUERY (lexonly index)."""
    indexes = {TEST_QUERY: fixture, LEXONLY_QUERY: lexonly}
    return {
        query: {
            name: _recall_hits(indexes[query], data_path / f"{i}-{name}", query, filters)
            for name, filters in variants.items()
        }
        for i, (query, variants) in enumerate(RECALL_VARIANTS.items())
    }


def _write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        idx = build_index(FIXTURE_VAULT, Path(tmp) / "data")
        lexonly = build_lexonly_index(Path(tmp) / "lexonly")
        _write(GOLDENS_PATH, compute_goldens(idx))
        _write(RECALL_GOLDENS_PATH, compute_recall_goldens(idx, lexonly, Path(tmp) / "recall"))


if __name__ == "__main__":
    main()
