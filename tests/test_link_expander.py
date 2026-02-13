"""Tests for the link expander."""

from unittest.mock import MagicMock

from secondbrain.retrieval.hybrid import RetrievalCandidate
from secondbrain.retrieval.link_expander import LinkExpander
from secondbrain.retrieval.reranker import RankedCandidate
from secondbrain.stores.lexical import LexicalStore


def _make_candidate(
    note_path: str,
    note_title: str,
    chunk_text: str,
    rerank_score: float = 0.9,
) -> RankedCandidate:
    return RankedCandidate(
        candidate=RetrievalCandidate(
            chunk_id=f"{note_path}_0",
            note_path=note_path,
            note_title=note_title,
            heading_path=[],
            chunk_text=chunk_text,
            similarity_score=0.8,
            bm25_score=0.5,
            rrf_score=0.7,
        ),
        rerank_score=rerank_score,
    )


def _make_expander(
    resolve_map: dict[str, str],
    chunk_map: dict[str, dict],
) -> LinkExpander:
    store = MagicMock(spec=LexicalStore)
    store.resolve_note_path.side_effect = lambda title: resolve_map.get(title)
    store.get_first_chunk.side_effect = lambda path: chunk_map.get(path)
    return LinkExpander(store)


class TestLinkExpander:
    def test_expands_linked_notes(self) -> None:
        candidates = [
            _make_candidate("notes/a.md", "Note A", "See [[Note B]] for more"),
        ]
        expander = _make_expander(
            resolve_map={"Note B": "notes/b.md"},
            chunk_map={"notes/b.md": {"note_title": "Note B", "chunk_text": "B content"}},
        )
        result = expander.expand(candidates)
        assert len(result) == 1
        assert result[0].note_path == "notes/b.md"
        assert result[0].note_title == "Note B"
        assert result[0].chunk_text == "B content"
        assert result[0].linked_from == "Note A"

    def test_skips_candidate_already_in_set(self) -> None:
        candidates = [
            _make_candidate("notes/a.md", "Note A", "See [[Note A]] self-link"),
        ]
        expander = _make_expander(
            resolve_map={"Note A": "notes/a.md"},
            chunk_map={},
        )
        result = expander.expand(candidates)
        assert result == []

    def test_skips_unresolvable_links(self) -> None:
        candidates = [
            _make_candidate("notes/a.md", "Note A", "See [[Missing Note]]"),
        ]
        expander = _make_expander(resolve_map={}, chunk_map={})
        result = expander.expand(candidates)
        assert result == []

    def test_caps_at_max_linked(self) -> None:
        candidates = [
            _make_candidate(
                "notes/a.md",
                "Note A",
                "See [[B]] and [[C]] and [[D]] and [[E]]",
            ),
        ]
        expander = _make_expander(
            resolve_map={
                "B": "notes/b.md",
                "C": "notes/c.md",
                "D": "notes/d.md",
                "E": "notes/e.md",
            },
            chunk_map={
                "notes/b.md": {"note_title": "B", "chunk_text": "B text"},
                "notes/c.md": {"note_title": "C", "chunk_text": "C text"},
                "notes/d.md": {"note_title": "D", "chunk_text": "D text"},
                "notes/e.md": {"note_title": "E", "chunk_text": "E text"},
            },
        )
        result = expander.expand(candidates, max_linked=3)
        assert len(result) == 3

    def test_no_links_returns_empty(self) -> None:
        candidates = [
            _make_candidate("notes/a.md", "Note A", "No links here"),
        ]
        expander = _make_expander(resolve_map={}, chunk_map={})
        result = expander.expand(candidates)
        assert result == []

    def test_dedup_across_candidates(self) -> None:
        candidates = [
            _make_candidate("notes/a.md", "Note A", "See [[Shared]]"),
            _make_candidate("notes/b.md", "Note B", "Also [[Shared]]"),
        ]
        expander = _make_expander(
            resolve_map={"Shared": "notes/shared.md"},
            chunk_map={"notes/shared.md": {"note_title": "Shared", "chunk_text": "shared text"}},
        )
        result = expander.expand(candidates)
        assert len(result) == 1
        assert result[0].linked_from == "Note A"

    def test_prefers_higher_scored_candidate_links(self) -> None:
        candidates = [
            _make_candidate("notes/a.md", "Note A", "See [[X]]", rerank_score=0.9),
            _make_candidate("notes/b.md", "Note B", "See [[Y]]", rerank_score=0.5),
        ]
        expander = _make_expander(
            resolve_map={"X": "notes/x.md", "Y": "notes/y.md"},
            chunk_map={
                "notes/x.md": {"note_title": "X", "chunk_text": "X text"},
                "notes/y.md": {"note_title": "Y", "chunk_text": "Y text"},
            },
        )
        result = expander.expand(candidates, max_linked=1)
        assert len(result) == 1
        assert result[0].note_title == "X"
