"""Spec 001 — store folder pre-filter (and the fixture kit it relies on)."""

import json
from unittest.mock import patch

from tests.fixtures.recall.capture_goldens import compute_goldens
from tests.fixtures.recall.index import GOLDENS_PATH, TEST_QUERY
from tests.fixtures.recall.stub_embedder import marker_similarity


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
