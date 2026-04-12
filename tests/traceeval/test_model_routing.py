"""Model routing tests — behavioral contract identified by TraceEval."""

from unittest.mock import MagicMock, patch

from secondbrain.indexing.context import ContextGenerator
from secondbrain.models import Chunk


def _make_chunk(**kwargs) -> Chunk:
    defaults = {
        "chunk_id": "test-chunk-1",
        "note_path": "notes/test.md",
        "note_title": "Test Note",
        "heading_path": ["Introduction"],
        "chunk_index": 0,
        "chunk_text": "This is a test chunk of text.",
        "checksum": "abc123",
    }
    defaults.update(kwargs)
    return Chunk(**defaults)


class TestContextGeneratorModelSelection:
    def test_default_model_is_haiku(self):
        gen = ContextGenerator(api_key="test-key")
        assert gen._model == "claude-haiku-4-5"

    def test_custom_model_accepted(self):
        gen = ContextGenerator(api_key="test-key", model="claude-sonnet-4-20250514")
        assert gen._model == "claude-sonnet-4-20250514"

    def test_model_passed_to_api_call(self):
        gen = ContextGenerator(api_key="test-key")

        # Build a mock response that matches the Anthropic messages.create shape
        mock_content_block = MagicMock()
        mock_content_block.text = "Context blurb text."
        mock_response = MagicMock()
        mock_response.content = [mock_content_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        gen._client = mock_client

        chunk = _make_chunk()
        gen.generate_blurbs("Test Note", "Full note content.", [chunk])

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs.get("model") == "claude-haiku-4-5"


class TestLLMClientModelSelection:
    def _mock_settings(self, **overrides):
        settings = MagicMock()
        settings.inbox_model = "claude-haiku-4-5"
        settings.anthropic_api_key = None
        settings.ollama_base_url = "http://127.0.0.1:11434/v1"
        settings.openai_api_key = None
        for k, v in overrides.items():
            setattr(settings, k, v)
        return settings

    @patch("secondbrain.scripts.llm_client.get_settings")
    def test_model_from_settings(self, mock_get_settings):
        mock_get_settings.return_value = self._mock_settings(inbox_model="claude-opus-4-5")

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient()
        assert client.model_name == "claude-opus-4-5"

    @patch("secondbrain.scripts.llm_client.get_settings")
    def test_anthropic_client_created_when_key_present(self, mock_get_settings):
        mock_get_settings.return_value = self._mock_settings(anthropic_api_key="sk-ant-test-key")

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient()
        assert client.anthropic_client is not None

    @patch("secondbrain.scripts.llm_client.get_settings")
    def test_anthropic_client_none_without_key(self, mock_get_settings):
        mock_get_settings.return_value = self._mock_settings(anthropic_api_key=None)

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient()
        assert client.anthropic_client is None
