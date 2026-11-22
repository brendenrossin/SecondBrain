"""Capture golden outputs of today's retrieval calls (spec 001 step 1.5).

Run on unchanged code, before any src/ change:

    uv run python -m tests.fixtures.recall.capture_goldens

It builds the fixture index into a temp dir with the stub embedder and writes
`goldens.json` next to this file. `test_existing_callers_unaffected` recomputes the
same structure on the changed code and compares.
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from secondbrain.retrieval.hybrid import HybridRetriever
from tests.fixtures.recall.index import (
    FIXTURE_VAULT,
    GOLDENS_PATH,
    TEST_QUERY,
    RecallIndex,
    build_index,
)

GOLDEN_QUERIES = [TEST_QUERY, "single owner stores", "harness"]


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


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        idx = build_index(FIXTURE_VAULT, Path(tmp) / "data")
        goldens = compute_goldens(idx)
    GOLDENS_PATH.write_text(json.dumps(goldens, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
