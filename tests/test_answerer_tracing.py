"""Tests for answerer trace_id threading and error logging."""

from unittest.mock import MagicMock

import pytest

from secondbrain.models import RetrievalLabel
from secondbrain.retrieval.hybrid import RetrievalCandidate
from secondbrain.retrieval.reranker import RankedCandidate
from secondbrain.synthesis.answerer import Answerer


def _make_candidate() -> RankedCandidate:
    return RankedCandidate(
        candidate=RetrievalCandidate(
            chunk_id="test_0",
            note_path="10_Notes/test.md",
            note_title="Test Note",
            heading_path=[],
            chunk_text="Some relevant content",
            similarity_score=0.8,
            bm25_score=0.5,
            rrf_score=0.7,
            note_folder="10_Notes",
            note_date="2026-01-15",
        ),
        rerank_score=0.9,
    )


def _make_anthropic_response(text="Answer text", input_tokens=200, output_tokens=100):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_response.usage.input_tokens = input_tokens
    mock_response.usage.output_tokens = output_tokens
    return mock_response


def _make_openai_response(content="Answer text", prompt_tokens=200, completion_tokens=100):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    mock_response.usage.prompt_tokens = prompt_tokens
    mock_response.usage.completion_tokens = completion_tokens
    return mock_response


class TestAnswerTraceIdPropagation:
    def test_anthropic_trace_id_passed_to_usage_store(self):
        mock_usage_store = MagicMock()
        answerer = Answerer(
            model="claude-haiku-4-5", provider="anthropic", usage_store=mock_usage_store
        )
        answerer._anthropic_client = MagicMock()
        answerer._anthropic_client.messages.create.return_value = _make_anthropic_response()

        candidates = [_make_candidate()]
        answerer.answer("test query", candidates, RetrievalLabel.PASS, trace_id="ans-trace-1")

        mock_usage_store.log_usage.assert_called_once()
        kwargs = mock_usage_store.log_usage.call_args.kwargs
        assert kwargs["trace_id"] == "ans-trace-1"
        assert kwargs["latency_ms"] is not None
        assert kwargs["latency_ms"] > 0

    def test_openai_trace_id_passed_to_usage_store(self):
        mock_usage_store = MagicMock()
        answerer = Answerer(model="gpt-4o-mini", provider="openai", usage_store=mock_usage_store)
        answerer._openai_client = MagicMock()
        answerer._openai_client.chat.completions.create.return_value = _make_openai_response()

        candidates = [_make_candidate()]
        answerer.answer("test query", candidates, RetrievalLabel.PASS, trace_id="ans-trace-2")

        mock_usage_store.log_usage.assert_called_once()
        kwargs = mock_usage_store.log_usage.call_args.kwargs
        assert kwargs["trace_id"] == "ans-trace-2"

    def test_no_trace_id_defaults_to_none(self):
        mock_usage_store = MagicMock()
        answerer = Answerer(
            model="claude-haiku-4-5", provider="anthropic", usage_store=mock_usage_store
        )
        answerer._anthropic_client = MagicMock()
        answerer._anthropic_client.messages.create.return_value = _make_anthropic_response()

        candidates = [_make_candidate()]
        answerer.answer("test query", candidates, RetrievalLabel.PASS)

        kwargs = mock_usage_store.log_usage.call_args.kwargs
        assert kwargs["trace_id"] is None


class TestAnswerErrorLogging:
    def test_anthropic_error_logs_with_correct_provider(self):
        mock_usage_store = MagicMock()
        answerer = Answerer(
            model="claude-haiku-4-5", provider="anthropic", usage_store=mock_usage_store
        )
        answerer._anthropic_client = MagicMock()
        answerer._anthropic_client.messages.create.side_effect = Exception("API timeout")

        candidates = [_make_candidate()]
        with pytest.raises(Exception, match="API timeout"):
            answerer.answer("test query", candidates, RetrievalLabel.PASS, trace_id="err-1")

        mock_usage_store.log_usage.assert_called_once()
        call = mock_usage_store.log_usage.call_args
        assert call[0][0] == "anthropic"
        assert call.kwargs["status"] == "error"
        assert "API timeout" in call.kwargs["error_message"]
        assert call.kwargs["trace_id"] == "err-1"
        assert call.kwargs["latency_ms"] > 0

    def test_openai_error_logs_with_correct_provider(self):
        mock_usage_store = MagicMock()
        answerer = Answerer(model="gpt-4o-mini", provider="openai", usage_store=mock_usage_store)
        answerer._openai_client = MagicMock()
        answerer._openai_client.chat.completions.create.side_effect = Exception("Rate limit")

        candidates = [_make_candidate()]
        with pytest.raises(Exception, match="Rate limit"):
            answerer.answer("test query", candidates, RetrievalLabel.PASS, trace_id="err-2")

        call = mock_usage_store.log_usage.call_args
        assert call[0][0] == "openai"

    def test_ollama_error_logs_with_ollama_provider(self):
        mock_usage_store = MagicMock()
        answerer = Answerer(
            model="llama3",
            provider="openai",
            base_url="http://localhost:11434/v1",
            usage_store=mock_usage_store,
        )
        answerer._openai_client = MagicMock()
        answerer._openai_client.chat.completions.create.side_effect = Exception(
            "Connection refused"
        )

        candidates = [_make_candidate()]
        with pytest.raises(Exception, match="Connection refused"):
            answerer.answer("test query", candidates, RetrievalLabel.PASS, trace_id="err-3")

        call = mock_usage_store.log_usage.call_args
        assert call[0][0] == "ollama"

    def test_error_reraises_after_logging(self):
        mock_usage_store = MagicMock()
        answerer = Answerer(
            model="claude-haiku-4-5", provider="anthropic", usage_store=mock_usage_store
        )
        answerer._anthropic_client = MagicMock()
        answerer._anthropic_client.messages.create.side_effect = RuntimeError("boom")

        candidates = [_make_candidate()]
        with pytest.raises(RuntimeError, match="boom"):
            answerer.answer("test query", candidates, RetrievalLabel.PASS)

        assert mock_usage_store.log_usage.call_count == 1


class TestNoResultsSkipsLLM:
    def test_no_results_label_returns_early(self):
        mock_usage_store = MagicMock()
        answerer = Answerer(
            model="claude-haiku-4-5", provider="anthropic", usage_store=mock_usage_store
        )

        result = answerer.answer("test", [], RetrievalLabel.NO_RESULTS, trace_id="skip-1")

        assert result == answerer.NO_RESULTS_RESPONSE
        mock_usage_store.log_usage.assert_not_called()
