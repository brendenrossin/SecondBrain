"""Functional tests for retrieval/reranker.py — score parsing fallbacks and retrieval labels."""

from unittest.mock import MagicMock, patch

from secondbrain.models import RetrievalLabel
from secondbrain.retrieval.hybrid import RetrievalCandidate
from secondbrain.retrieval.reranker import LLMReranker


def _make_candidate(
    chunk_id: str = "abc",
    similarity: float = 0.5,
    text: str = "Some chunk text",
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk_id,
        note_path="test.md",
        note_title="Test Note",
        heading_path=["Section"],
        chunk_text=text,
        similarity_score=similarity,
        bm25_score=1.0,
        rrf_score=0.02,
        note_folder="10_Notes",
        note_date="2026-01-01",
    )


def _make_anthropic_reranker(mock_response_text: str) -> tuple[LLMReranker, MagicMock]:
    """Create a reranker with a mocked Anthropic client."""
    reranker = LLMReranker(provider="anthropic")
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=mock_response_text)]
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 10
    mock_client.messages.create.return_value = mock_response
    reranker._anthropic_client = mock_client
    return reranker, mock_client


class TestScoreParsing:
    """Tests for _score_candidates_batch JSON/regex/similarity fallback chain."""

    def test_valid_json_array(self):
        reranker, _ = _make_anthropic_reranker("[8.5, 3.0]")
        candidates = [_make_candidate("a"), _make_candidate("b")]
        scores = reranker._score_candidates_batch("query", candidates)
        assert scores == [8.5, 3.0]

    def test_invalid_json_falls_back_to_regex(self):
        # No stray numbers — regex should cleanly extract 7.5 and 4.0
        reranker, _ = _make_anthropic_reranker("First chunk: 7.5, Second chunk: 4.0")
        candidates = [_make_candidate("a"), _make_candidate("b")]
        scores = reranker._score_candidates_batch("query", candidates)
        assert scores == [7.5, 4.0]

    def test_wrong_length_json_falls_back_to_regex(self):
        reranker, _ = _make_anthropic_reranker("[8.5]")
        candidates = [_make_candidate("a"), _make_candidate("b")]
        scores = reranker._score_candidates_batch("query", candidates)
        # JSON has 1 element but need 2 → regex finds "8" and "5" from "8.5"
        # Actually regex finds "8.5" — only 1 number, not enough for 2 candidates
        # Falls back to similarity * 10
        assert scores == [5.0, 5.0]

    def test_no_numbers_falls_back_to_similarity(self):
        reranker, _ = _make_anthropic_reranker("I cannot score these chunks.")
        candidates = [
            _make_candidate("a", similarity=0.8),
            _make_candidate("b", similarity=0.4),
        ]
        scores = reranker._score_candidates_batch("query", candidates)
        assert scores == [8.0, 4.0]  # similarity * 10

    def test_llm_exception_falls_back_to_similarity(self):
        reranker = LLMReranker(provider="anthropic")
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API timeout")
        reranker._anthropic_client = mock_client

        candidates = [_make_candidate("a", similarity=0.6)]
        scores = reranker._score_candidates_batch("query", candidates)
        assert scores == [6.0]  # similarity * 10


class TestRetrievalLabels:
    """Tests for the retrieval label assignment logic."""

    def test_no_candidates_returns_no_results(self):
        reranker = LLMReranker()
        ranked, label = reranker.rerank("query", [])
        assert label == RetrievalLabel.NO_RESULTS
        assert ranked == []

    def test_normal_results_return_pass(self):
        reranker = LLMReranker(rerank_threshold=5.0)
        candidates = [_make_candidate("a", similarity=0.5)]

        with patch.object(reranker, "_score_candidates_batch", return_value=[7.0]):
            ranked, label = reranker.rerank("query", candidates, top_n=5)

        assert label == RetrievalLabel.PASS
        assert len(ranked) == 1
        assert ranked[0].rerank_score == 7.0

    def test_all_low_scores_return_irrelevant(self):
        reranker = LLMReranker(rerank_threshold=5.0)
        candidates = [_make_candidate("a"), _make_candidate("b")]

        with patch.object(reranker, "_score_candidates_batch", return_value=[2.0, 1.0]):
            _, label = reranker.rerank("query", candidates, top_n=5)

        assert label == RetrievalLabel.IRRELEVANT

    def test_hallucination_risk_detected(self):
        reranker = LLMReranker(hallucination_threshold=3.0)
        # High similarity but low rerank score
        candidates = [_make_candidate("a", similarity=0.8)]

        with patch.object(reranker, "_score_candidates_batch", return_value=[2.0]):
            _, label = reranker.rerank("query", candidates, top_n=5)

        assert label == RetrievalLabel.HALLUCINATION_RISK


class TestRanking:
    """Tests for the ranking and top_n behavior."""

    def test_top_n_limits_output(self):
        reranker = LLMReranker()
        candidates = [_make_candidate(f"c{i}") for i in range(10)]
        scores = list(range(10, 0, -1))  # 10, 9, 8, ...

        with patch.object(
            reranker, "_score_candidates_batch", return_value=[float(s) for s in scores]
        ):
            ranked, _ = reranker.rerank("query", candidates, top_n=3)

        assert len(ranked) == 3

    def test_results_sorted_by_rerank_score_descending(self):
        reranker = LLMReranker()
        candidates = [_make_candidate("a"), _make_candidate("b"), _make_candidate("c")]

        with patch.object(reranker, "_score_candidates_batch", return_value=[3.0, 9.0, 6.0]):
            ranked, _ = reranker.rerank("query", candidates, top_n=5)

        scores = [r.rerank_score for r in ranked]
        assert scores == sorted(scores, reverse=True)
        assert ranked[0].candidate.chunk_id == "b"  # highest score


class TestOpenAIProvider:
    """Tests for the OpenAI/Ollama provider path."""

    def test_openai_provider_json_parsing(self):
        reranker = LLMReranker(provider="openai", api_key="test-key")
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "[8.0]"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 10
        mock_client.chat.completions.create.return_value = mock_response
        reranker._openai_client = mock_client

        candidates = [_make_candidate("a")]
        scores = reranker._score_candidates_batch("query", candidates)
        assert scores == [8.0]
