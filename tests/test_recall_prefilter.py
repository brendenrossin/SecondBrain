"""Spec 001 — store folder pre-filter (and the fixture kit it relies on)."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest
from chromadb.errors import ChromaError

from secondbrain.models import Chunk
from secondbrain.retrieval.hybrid import HybridRetriever
from secondbrain.stores.lexical import LexicalStore
from secondbrain.stores.vector import VectorStore
from tests.fixtures.recall.capture_goldens import compute_goldens, trace_lexical_sql
from tests.fixtures.recall.index import (
    GOLDENS_PATH,
    TEST_QUERY,
    build_index,
    note,
    write_vault,
)
from tests.fixtures.recall.stub_embedder import DIM, make_stub_embedder, marker_similarity


def test_fixture_index_builds(recall_index):
    """The session fixture index holds every Background note with stub cosines."""
    lexical = recall_index.lexical_store
    rows = lexical.conn.execute(
        "SELECT chunk_id, note_path, note_folder, chunk_text FROM chunks ORDER BY note_path"
    ).fetchall()
    paths = {r["note_path"] for r in rows}
    assert paths == {
        "10_Notes/review-process.md",
        "Witt/Learnings/pin-the-docstring.md",
        "Witt/Projects/second-brain/decisions/ADR-001-thin.md",
        "Witt/Projects/second-brain/second-brain.md",
        "Witt/Projects/witt-tools/specs/x.md",
        "Witt/Projects/witt/decisions/ADR-001-overrides.md",
        "Witt/Projects/witt/scratch.md",
        "Witt/Projects/witt/specs/001-harness.md",
    }
    assert {r["note_folder"] for r in rows if r["note_path"].startswith("Witt/")} == {"Witt"}
    assert recall_index.vector_store.count() == len(rows)

    query_vec = recall_index.embedder.embed_single(TEST_QUERY)
    results = recall_index.vector_store.search(query_vec, top_k=50)
    by_id = {cid: sim for cid, sim, _meta, _doc in results}
    for r in rows:
        assert abs(by_id[r["chunk_id"]] - marker_similarity(r["chunk_text"])) < 1e-5


def test_existing_callers_unaffected(recall_index):
    """Scenario: existing callers are unaffected (goldens captured on main).

    No new kwargs → results equal the goldens, collection.query gets no "where" key,
    and the lexical SQL text + bound params equal today's.
    """
    goldens = json.loads(GOLDENS_PATH.read_text(encoding="utf-8"))
    collection = recall_index.vector_store.collection
    with patch.object(collection, "query", wraps=collection.query) as spy:
        actual = compute_goldens(recall_index)

    assert actual == goldens
    assert spy.call_count > 0
    for call in spy.call_args_list:
        assert "where" not in call.kwargs


# --- Vector store -----------------------------------------------------------------

_QUERY_VEC = np.eye(DIM, dtype=np.float32)[0]


def _fake_query_result() -> dict:
    return {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}


def test_vector_store_receives_folder_filter(tmp_path):
    """Scenario: stores receive the filter before the limit (vector half)."""
    store = VectorStore(tmp_path / "chroma")
    store._collection = MagicMock()
    store._collection.query.return_value = _fake_query_result()

    store.search(_QUERY_VEC, top_k=7, include_folders=["Witt"])

    kwargs = store._collection.query.call_args.kwargs
    assert kwargs["where"] == {"note_folder": {"$in": ["Witt"]}}
    assert kwargs["n_results"] == 7


def test_vector_filter_applied_on_reconnect_retry(tmp_path):
    """Scenario: the filter is applied on the reconnect retry (vector)."""
    store = VectorStore(tmp_path / "chroma")
    first, second = MagicMock(), MagicMock()
    first.query.side_effect = ChromaError("boom")
    second.query.return_value = _fake_query_result()
    store._collection = first
    with patch.object(VectorStore, "collection", new_callable=PropertyMock) as prop:
        prop.side_effect = [first, second]
        store.search(_QUERY_VEC, include_folders=["Witt"])

    assert second.query.call_args.kwargs["where"] == {"note_folder": {"$in": ["Witt"]}}


def _window_vault(root: Path) -> Path:
    notes = {
        f"Witt/Projects/witt/specs/w{i:02d}.md": note(f"W{i}", 0.31 + i * 0.01, f"witt note {i}")
        for i in range(12)
    }
    notes |= {
        f"10_Notes/n{i:03d}.md": note(f"N{i}", 0.95, f"outranking note {i}") for i in range(150)
    }
    return write_vault(root, notes)


def test_vector_window_returns_every_witt_chunk(tmp_path):
    """Scenario: the vector window returns every Witt chunk (real Chroma)."""
    idx = build_index(_window_vault(tmp_path / "vault"), tmp_path / "data")

    results = idx.vector_store.search(
        _QUERY_VEC, top_k=12, min_similarity=0.3, include_folders=["Witt"]
    )

    ids = {cid for cid, _sim, _meta, _doc in results}
    assert len(ids) == len(results) == 12
    assert all(meta["note_folder"] == "Witt" for _cid, _sim, meta, _doc in results)
    assert len(ids) == idx.lexical_store.count_chunks(["Witt"])


# --- Lexical store ----------------------------------------------------------------


def _chunk(i: int, folder: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=f"{folder}-{i}",
        note_path=f"{folder}/n{i}.md",
        note_title=f"n{i}",
        heading_path=[],
        chunk_index=0,
        chunk_text=text,
        checksum="x",
        note_folder=folder,
    )


def test_lexical_store_filters_before_limit(tmp_path):
    """Scenario: stores receive the filter before the limit (lexical half).

    55 10_Notes chunks with higher BM25 than the 5 Witt chunks; top_k 50.
    """
    store = LexicalStore(tmp_path / "lexical.db")
    strong = "zebra " * 20
    weak = "zebra " + "filler " * 40
    store.add_chunks(
        [_chunk(i, "10_Notes", strong) for i in range(55)]
        + [_chunk(i, "Witt", weak) for i in range(5)]
    )
    assert {cid for cid, _ in store.search("zebra", top_k=50)} & {
        f"Witt-{i}" for i in range(5)
    } == set()

    statements = trace_lexical_sql(store.conn)
    results = store.search("zebra", top_k=50, include_folders=["Witt"])
    store.conn.set_trace_callback(None)

    assert {cid for cid, _ in results} == {f"Witt-{i}" for i in range(5)}
    top = [s for s in statements if not s.lstrip().startswith("--")]
    assert "c.note_folder IN ('Witt')" in top[0]  # the trace shows the bound value


def test_lexical_folder_values_bound_as_parameters(tmp_path):
    """The folder values are bound as SQL parameters, never formatted into the SQL."""
    store = LexicalStore(tmp_path / "lexical.db")
    store.add_chunks([_chunk(0, "Witt", "zebra " * 20)])
    conn = MagicMock(wraps=store.conn)
    with patch.object(LexicalStore, "conn", new_callable=PropertyMock, return_value=conn):
        store.search("zebra", include_folders=["Witt", "x') OR 1=1 --"])

    sql, params = conn.execute.call_args.args
    assert "Witt" not in sql and "OR 1=1" not in sql
    assert "IN (?,?)" in sql
    assert params == ("Witt", "x') OR 1=1 --", '"zebra"', 50)


def _failing_conn() -> MagicMock:
    conn = MagicMock()
    conn.execute.side_effect = sqlite3.DatabaseError("disk image is malformed")
    return conn


def test_lexical_filter_applied_on_reconnect_retry(tmp_path):
    """Scenario: the filter is applied on the reconnect retry (lexical).

    The first query fails; the retry runs on a fresh connection and must still filter
    (the 10_Notes chunk matches the query too).
    """
    store = LexicalStore(tmp_path / "lexical.db")
    store.add_chunks([_chunk(0, "Witt", "zebra " * 20), _chunk(1, "10_Notes", "zebra " * 20)])
    store._conn = _failing_conn()

    results = store.search("zebra", include_folders=["Witt"])

    assert [cid for cid, _ in results] == ["Witt-0"]


def test_count_chunks_counts_only_listed_folders(tmp_path):
    """Scenario: count_chunks counts only the listed folders."""
    store = LexicalStore(tmp_path / "lexical.db")
    store.add_chunks(
        [_chunk(i, "Witt", "w " * 60) for i in range(7)]
        + [_chunk(i, "10_Notes", "n " * 60) for i in range(40)]
    )
    assert store.count_chunks(["Witt"]) == 7
    assert store.count_chunks(["Witt", "10_Notes"]) == 47


def test_count_chunks_retries_after_database_error(tmp_path):
    store = LexicalStore(tmp_path / "lexical.db")
    store.add_chunks([_chunk(0, "Witt", "w " * 60), _chunk(1, "10_Notes", "n " * 60)])
    store._conn = _failing_conn()

    assert store.count_chunks(["Witt"]) == 1


# --- Hybrid retriever -------------------------------------------------------------


def test_prefilter_survives_crowding(tmp_path):
    """Scenario: the pre-filter survives crowding (real stores).

    3 10_Notes chunks outrank 1 Witt chunk in both stores; k_vec = k_lex = 2.
    """
    strong = "crowding zebra " * 15
    vault = write_vault(
        tmp_path / "vault",
        {
            **{f"10_Notes/c{i}.md": note(f"C{i}", 0.9, strong + f" c{i}") for i in range(3)},
            "Witt/Learnings/w.md": note("W", 0.5, "zebra " + "quiet words " * 15),
        },
    )
    idx = build_index(vault, tmp_path / "data")
    retriever = HybridRetriever(idx.vector_store, idx.lexical_store, idx.embedder, k_vec=2, k_lex=2)
    assert "Witt/Learnings/w.md" not in {c.note_path for c in retriever.retrieve("zebra")}

    results = retriever.retrieve("zebra", include_folders=["Witt"])

    assert [c.note_path for c in results] == ["Witt/Learnings/w.md"]
    assert results[0].similarity_score == pytest.approx(0.5, abs=1e-5)
    assert results[0].bm25_score > 0


def test_empty_folder_list_is_an_error():
    """Scenario: an empty folder list is an error."""
    retriever = HybridRetriever(MagicMock(), MagicMock(), make_stub_embedder())
    with pytest.raises(ValueError, match="include_folders must be non-empty"):
        retriever.retrieve("q", include_folders=[])
