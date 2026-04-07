"""Tests for the ask API endpoint — stream error handling, warmup, and empty answer guard."""

import json
from unittest.mock import MagicMock, patch

from secondbrain.api.dependencies import (
    get_conversation_store,
    get_link_expander,
    get_query_logger,
    get_retriever,
)
from secondbrain.main import app
from secondbrain.models import RetrievalLabel


def _setup_stream_overrides(answerer_side_effect=None):
    """Set up DI overrides and patches for ask/stream tests.

    Returns (overrides_dict, mock_conv, patches_to_start).
    The reranker/answerer are selected via get_reranker()/get_answerer() (not DI),
    so we patch them at the module level.
    """
    mock_retriever = MagicMock()
    mock_retriever.retrieve.return_value = []

    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = ([], RetrievalLabel.NO_RESULTS)

    mock_answerer = MagicMock()
    if answerer_side_effect:
        mock_answerer.answer_stream.side_effect = answerer_side_effect
    else:
        mock_answerer.answer_stream.return_value = iter([])

    mock_conv = MagicMock()
    mock_conv.get_or_create_conversation.return_value = "test-conv-id"
    mock_conv.get_recent_messages.return_value = []

    mock_logger = MagicMock()
    mock_link = MagicMock()
    mock_link.expand.return_value = ""

    overrides = {
        get_retriever: lambda: mock_retriever,
        get_conversation_store: lambda: mock_conv,
        get_query_logger: lambda: mock_logger,
        get_link_expander: lambda: mock_link,
    }

    # Reranker/answerer are called directly (not via Depends), so patch them
    patches = [
        patch("secondbrain.api.ask.get_reranker", return_value=mock_reranker),
        patch("secondbrain.api.ask.get_answerer", return_value=mock_answerer),
    ]

    return overrides, mock_conv, patches


class TestWarmupEndpoint:
    def test_warmup_returns_warming_status(self, client):
        with patch("secondbrain.api.ask.OpenAI"):
            resp = client.post("/api/v1/warmup")
        assert resp.status_code == 200
        assert resp.json() == {"status": "warming"}

    def test_warmup_handles_ollama_down(self, client):
        with patch("secondbrain.api.ask.OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.side_effect = Exception(
                "Connection refused"
            )
            resp = client.post("/api/v1/warmup")
        assert resp.status_code == 200
        assert resp.json() == {"status": "warming"}


class TestStreamErrorHandling:
    """Test that stream errors emit a generic error event, not internal details."""

    def test_stream_error_returns_generic_message(self, client):
        """When answer_stream raises, the SSE error event should not leak exception details."""
        overrides, _, patches = _setup_stream_overrides(
            answerer_side_effect=Exception("Internal DB error at /secret/path/db.sqlite")
        )
        app.dependency_overrides.update(overrides)
        [p.start() for p in patches]
        try:
            resp = client.post(
                "/api/v1/ask/stream",
                json={"query": "test query"},
            )
            assert resp.status_code == 200

            events = _parse_sse(resp.text)
            error_events = [e for e in events if e["event"] == "error"]
            assert len(error_events) == 1

            error_data = json.loads(error_events[0]["data"])
            assert "/secret/path" not in error_data["message"]
            assert error_data["message"] == "An error occurred while generating the response."
        finally:
            for p in patches:
                p.stop()
            for key in overrides:
                app.dependency_overrides.pop(key, None)

    def test_empty_answer_not_saved_to_conversation(self, client):
        """When stream errors before any tokens, no blank assistant turn is saved."""
        overrides, mock_conv, patches = _setup_stream_overrides(
            answerer_side_effect=Exception("boom")
        )
        app.dependency_overrides.update(overrides)
        [p.start() for p in patches]
        try:
            client.post(
                "/api/v1/ask/stream",
                json={"query": "test query"},
            )
            mock_conv.add_message.assert_not_called()
        finally:
            for p in patches:
                p.stop()
            for key in overrides:
                app.dependency_overrides.pop(key, None)


class TestRerankerCoTFallback:
    """Test that CoT reasoning text doesn't corrupt score extraction."""

    def test_cot_reasoning_before_json_array(self):
        """When model outputs reasoning text followed by a JSON array, extract the array."""
        from secondbrain.retrieval.reranker import LLMReranker

        response_text = (
            "Let me analyze these 3 chunks. Chunk 1 is about databases, "
            "chunk 2 covers APIs, chunk 3 is irrelevant. "
            "My scores: [8.5, 6.0, 2.0]"
        )

        reranker = LLMReranker(provider="anthropic")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=response_text)]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response
        reranker._anthropic_client = mock_client

        candidates = [_make_candidate("a"), _make_candidate("b"), _make_candidate("c")]
        scores = reranker._score_candidates_batch("query", candidates)
        assert scores == [8.5, 6.0, 2.0]

    def test_scores_clamped_to_valid_range(self):
        """Out-of-range scores from a misbehaving model are clamped to [0, 10]."""
        from secondbrain.retrieval.reranker import LLMReranker

        reranker = LLMReranker(provider="anthropic")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="[100, -5, 0.5]")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 10
        mock_client.messages.create.return_value = mock_response
        reranker._anthropic_client = mock_client

        candidates = [_make_candidate("a"), _make_candidate("b"), _make_candidate("c")]
        scores = reranker._score_candidates_batch("query", candidates)
        assert scores == [10.0, 0.0, 0.5]


def _make_candidate(chunk_id: str = "abc"):
    from secondbrain.retrieval.hybrid import RetrievalCandidate

    return RetrievalCandidate(
        chunk_id=chunk_id,
        note_path="test.md",
        note_title="Test Note",
        heading_path=["Section"],
        chunk_text="Some chunk text",
        similarity_score=0.5,
        bm25_score=1.0,
        rrf_score=0.02,
        note_folder="10_Notes",
        note_date="2026-01-01",
    )


def _parse_sse(text: str) -> list[dict]:
    """Parse SSE text into a list of {event, data} dicts."""
    events = []
    current_event = ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            events.append({"event": current_event, "data": line[6:]})
    return events
