"""Tests for answerer linked context integration."""

from secondbrain.retrieval.hybrid import RetrievalCandidate
from secondbrain.retrieval.link_expander import LinkedContext
from secondbrain.retrieval.reranker import RankedCandidate
from secondbrain.synthesis.answerer import Answerer


def _make_candidate(
    note_path: str = "10_Notes/test.md",
    note_title: str = "Test Note",
    chunk_text: str = "Some content here",
    note_folder: str = "10_Notes",
    note_date: str = "2026-01-15",
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
            note_folder=note_folder,
            note_date=note_date,
        ),
        rerank_score=0.9,
    )


class TestBuildContextWithLinkedNotes:
    def test_no_linked_context(self) -> None:
        answerer = Answerer(model="test", provider="openai")
        candidates = [_make_candidate()]
        context = answerer._build_context(candidates)
        assert "CONNECTED NOTES" not in context
        assert "[1]" in context

    def test_with_linked_context(self) -> None:
        answerer = Answerer(model="test", provider="openai")
        candidates = [_make_candidate()]
        linked = [
            LinkedContext(
                note_path="30_Concepts/linked.md",
                note_title="Linked Note",
                chunk_text="Linked content here",
                linked_from="Test Note",
            )
        ]
        context = answerer._build_context(candidates, linked)
        assert "CONNECTED NOTES (linked from retrieved results):" in context
        assert "[C1]" in context
        assert "[30_Concepts]" in context
        assert "Linked Note (linked from: Test Note)" in context
        assert "Linked content here" in context

    def test_multiple_linked_notes(self) -> None:
        answerer = Answerer(model="test", provider="openai")
        candidates = [_make_candidate()]
        linked = [
            LinkedContext(
                note_path="10_Notes/a.md",
                note_title="Note A",
                chunk_text="A content",
                linked_from="Test Note",
            ),
            LinkedContext(
                note_path="20_Projects/b.md",
                note_title="Note B",
                chunk_text="B content",
                linked_from="Test Note",
            ),
        ]
        context = answerer._build_context(candidates, linked)
        assert "[C1]" in context
        assert "[C2]" in context
        assert "[10_Notes]" in context
        assert "[20_Projects]" in context

    def test_linked_context_no_folder(self) -> None:
        answerer = Answerer(model="test", provider="openai")
        candidates = [_make_candidate()]
        linked = [
            LinkedContext(
                note_path="note.md",
                note_title="Root Note",
                chunk_text="Root content",
                linked_from="Test Note",
            )
        ]
        context = answerer._build_context(candidates, linked)
        assert "[C1] Root Note" in context
        # No folder bracket when note is at root
        assert "[C1] [" not in context

    def test_system_prompt_includes_connected_notes_rule(self) -> None:
        assert "connected notes" in Answerer.SYSTEM_PROMPT
        assert "linked from the retrieved sources" in Answerer.SYSTEM_PROMPT
