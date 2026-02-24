"""Tests for the LLM client with Anthropic provider support."""

from unittest.mock import MagicMock, patch


class TestLLMClientAnthropicProvider:
    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    def test_anthropic_success(self, mock_anthropic_cls, mock_settings):
        """Test that Anthropic is tried first and returns successfully."""
        settings = MagicMock()
        settings.anthropic_api_key = "test-key"
        settings.inbox_model = "claude-sonnet-4-5"
        settings.ollama_model = "gpt-oss:20b"
        settings.ollama_base_url = "http://127.0.0.1:11434/v1"
        settings.openai_api_key = None
        mock_settings.return_value = settings

        # Mock Anthropic response
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Anthropic response")]
        mock_client.messages.create.return_value = mock_response

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient()
        result = client.chat("system prompt", "user prompt")

        assert result == "Anthropic response"
        mock_client.messages.create.assert_called_once()

    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    @patch("secondbrain.scripts.llm_client.OpenAI")
    def test_fallback_to_ollama_on_anthropic_failure(
        self, mock_openai_cls, mock_anthropic_cls, mock_settings
    ):
        """Test fallback to Ollama when Anthropic fails."""
        settings = MagicMock()
        settings.anthropic_api_key = "test-key"
        settings.inbox_model = "claude-sonnet-4-5"
        settings.ollama_model = "gpt-oss:20b"
        settings.ollama_base_url = "http://127.0.0.1:11434/v1"
        settings.openai_api_key = None
        mock_settings.return_value = settings

        # Anthropic fails
        mock_anthropic = MagicMock()
        mock_anthropic_cls.return_value = mock_anthropic
        mock_anthropic.messages.create.side_effect = Exception("Anthropic error")

        # Ollama succeeds
        mock_ollama = MagicMock()
        mock_openai_cls.return_value = mock_ollama
        mock_oai_response = MagicMock()
        mock_oai_response.choices = [MagicMock(message=MagicMock(content="Ollama response"))]
        mock_ollama.chat.completions.create.return_value = mock_oai_response

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient()
        result = client.chat("system prompt", "user prompt")

        assert result == "Ollama response"

    @patch("secondbrain.scripts.llm_client.get_settings")
    def test_no_anthropic_key_skips_to_ollama(self, mock_settings):
        """Test that without an Anthropic key, Ollama is tried directly."""
        settings = MagicMock()
        settings.anthropic_api_key = None
        settings.inbox_model = "claude-sonnet-4-5"
        settings.ollama_model = "gpt-oss:20b"
        settings.ollama_base_url = "http://127.0.0.1:11434/v1"
        settings.openai_api_key = None
        mock_settings.return_value = settings

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient()
        # anthropic_client property should return None
        assert client.anthropic_client is None


class TestUsageType:
    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    def test_custom_usage_type_passed_to_log(self, mock_anthropic_cls, mock_settings):
        """Test that custom usage_type is passed through to _log_usage()."""
        settings = MagicMock()
        settings.anthropic_api_key = "test-key"
        settings.inbox_model = "claude-sonnet-4-5"
        settings.openai_api_key = None
        mock_settings.return_value = settings

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="response")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        mock_usage_store = MagicMock()

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient(usage_store=mock_usage_store, usage_type="extraction")
        client.chat("system", "user")

        # Verify usage_store.log_usage was called with extraction type
        mock_usage_store.log_usage.assert_called_once()
        call_args = mock_usage_store.log_usage.call_args
        assert call_args[0][2] == "extraction"  # usage_type is 3rd positional arg

    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    def test_default_usage_type_is_inbox(self, mock_anthropic_cls, mock_settings):
        """Test that default usage_type is 'inbox' for backwards compatibility."""
        settings = MagicMock()
        settings.anthropic_api_key = "test-key"
        settings.inbox_model = "claude-sonnet-4-5"
        settings.openai_api_key = None
        mock_settings.return_value = settings

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="response")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_client.messages.create.return_value = mock_response

        mock_usage_store = MagicMock()

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient(usage_store=mock_usage_store)
        client.chat("system", "user")

        mock_usage_store.log_usage.assert_called_once()
        call_args = mock_usage_store.log_usage.call_args
        assert call_args[0][2] == "inbox"
