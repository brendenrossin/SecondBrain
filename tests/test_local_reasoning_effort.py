"""Tests for switching off local-model reasoning on the Ollama path.

Gemma 4 and other local reasoning models spend their whole ``max_tokens``
budget on internal reasoning unless it is disabled, which leaves
``message.content`` empty and makes the answerer return "" with no error. The
guard is a ``reasoning_effort: none`` field sent only to local models.
"""

from unittest.mock import MagicMock, patch

from secondbrain.models import RetrievalLabel
from secondbrain.retrieval.hybrid import RetrievalCandidate
from secondbrain.retrieval.reranker import LLMReranker, RankedCandidate, local_extra_body
from secondbrain.synthesis.answerer import Answerer

OLLAMA_URL = "http://127.0.0.1:11434/v1"
REASONING_OFF = {"reasoning_effort": "none"}


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


def _make_openai_response(content="Answer text"):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    mock_response.usage.prompt_tokens = 200
    mock_response.usage.completion_tokens = 100
    return mock_response


def _make_stream_chunk(content):
    chunk = MagicMock()
    chunk.choices = [MagicMock(delta=MagicMock(content=content))]
    chunk.usage = None
    return chunk


class TestLocalExtraBody:
    def test_disables_reasoning_for_local_model(self):
        assert local_extra_body(OLLAMA_URL) == REASONING_OFF

    def test_sends_nothing_extra_for_cloud_model(self):
        assert local_extra_body(None) == {}


class TestAnswererPassesExtraBody:
    def test_local_answer_request_disables_reasoning(self):
        answerer = Answerer(model="gemma4", base_url=OLLAMA_URL, provider="openai")
        answerer._openai_client = MagicMock()
        answerer._openai_client.chat.completions.create.return_value = _make_openai_response()

        answerer.answer("test query", [_make_candidate()], RetrievalLabel.PASS)

        kwargs = answerer._openai_client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"] == REASONING_OFF

    def test_cloud_answer_request_leaves_reasoning_alone(self):
        answerer = Answerer(model="gpt-4o-mini", provider="openai")
        answerer._openai_client = MagicMock()
        answerer._openai_client.chat.completions.create.return_value = _make_openai_response()

        answerer.answer("test query", [_make_candidate()], RetrievalLabel.PASS)

        kwargs = answerer._openai_client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"] == {}

    def test_local_stream_request_disables_reasoning(self):
        answerer = Answerer(model="gemma4", base_url=OLLAMA_URL, provider="openai")
        answerer._openai_client = MagicMock()
        answerer._openai_client.chat.completions.create.return_value = iter(
            [_make_stream_chunk("hello")]
        )

        list(answerer.answer_stream("test query", [_make_candidate()], RetrievalLabel.PASS))

        kwargs = answerer._openai_client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"] == REASONING_OFF

    def test_cloud_stream_request_omits_extra_body(self):
        answerer = Answerer(model="gpt-4o-mini", provider="openai")
        answerer._openai_client = MagicMock()
        answerer._openai_client.chat.completions.create.return_value = iter(
            [_make_stream_chunk("hello")]
        )

        list(answerer.answer_stream("test query", [_make_candidate()], RetrievalLabel.PASS))

        kwargs = answerer._openai_client.chat.completions.create.call_args.kwargs
        assert "extra_body" not in kwargs
        assert kwargs["stream_options"] == {"include_usage": True}

    def test_local_answer_still_returns_content(self):
        answerer = Answerer(model="gemma4", base_url=OLLAMA_URL, provider="openai")
        answerer._openai_client = MagicMock()
        answerer._openai_client.chat.completions.create.return_value = _make_openai_response(
            content="Grounded answer [1]"
        )

        result = answerer.answer("test query", [_make_candidate()], RetrievalLabel.PASS)

        assert result == "Grounded answer [1]"


class TestRerankerPassesExtraBody:
    def test_local_rerank_request_disables_reasoning(self):
        reranker = LLMReranker(model="gemma4", base_url=OLLAMA_URL, provider="openai")
        reranker._openai_client = MagicMock()
        reranker._openai_client.chat.completions.create.return_value = _make_openai_response(
            content="[8.0]"
        )

        reranker._score_candidates_batch("test query", [_make_candidate().candidate])

        kwargs = reranker._openai_client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"] == REASONING_OFF

    def test_cloud_rerank_request_leaves_reasoning_alone(self):
        reranker = LLMReranker(model="gpt-4o-mini", provider="openai")
        reranker._openai_client = MagicMock()
        reranker._openai_client.chat.completions.create.return_value = _make_openai_response(
            content="[8.0]"
        )

        reranker._score_candidates_batch("test query", [_make_candidate().candidate])

        kwargs = reranker._openai_client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"] == {}


class TestLocalProviderModelSplit:
    def _mock_settings(self):
        settings = MagicMock()
        settings.ollama_model = "gemma4:26b-a4b-it-qat"
        settings.ollama_rerank_model = "llama3.2:3b"
        settings.ollama_base_url = OLLAMA_URL
        return settings

    @patch("secondbrain.api.dependencies.get_usage_store")
    @patch("secondbrain.api.dependencies.get_settings")
    def test_local_reranker_uses_the_small_model(self, mock_settings, mock_usage_store):
        from secondbrain.api.dependencies import get_local_reranker

        mock_settings.return_value = self._mock_settings()
        mock_usage_store.return_value = MagicMock()
        get_local_reranker.cache_clear()

        assert get_local_reranker().model == "llama3.2:3b"
        get_local_reranker.cache_clear()

    @patch("secondbrain.api.dependencies.get_vault_manifest")
    @patch("secondbrain.api.dependencies.get_usage_store")
    @patch("secondbrain.api.dependencies.get_settings")
    def test_local_answerer_uses_the_synthesis_model(
        self, mock_settings, mock_usage_store, mock_manifest
    ):
        from secondbrain.api.dependencies import get_local_answerer

        mock_settings.return_value = self._mock_settings()
        mock_usage_store.return_value = MagicMock()
        mock_manifest.return_value = None
        get_local_answerer.cache_clear()

        assert get_local_answerer().model == "gemma4:26b-a4b-it-qat"
        get_local_answerer.cache_clear()
