"""Tests for the LLM client with Anthropic provider support."""

from unittest.mock import MagicMock, patch


def _make_settings(**overrides):
    settings = MagicMock()
    settings.anthropic_api_key = overrides.get("anthropic_api_key", "test-key")
    settings.inbox_model = overrides.get("inbox_model", "claude-sonnet-4-5")
    settings.ollama_model = overrides.get("ollama_model", "gpt-oss:20b")
    settings.ollama_base_url = overrides.get("ollama_base_url", "http://127.0.0.1:11434/v1")
    settings.openai_api_key = overrides.get("openai_api_key")
    return settings


def _make_anthropic_response(text="response", input_tokens=100, output_tokens=50):
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_response.usage.input_tokens = input_tokens
    mock_response.usage.output_tokens = output_tokens
    return mock_response


def _make_openai_response(content="response", prompt_tokens=100, completion_tokens=50):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    mock_response.usage.prompt_tokens = prompt_tokens
    mock_response.usage.completion_tokens = completion_tokens
    return mock_response


class TestLLMClientAnthropicProvider:
    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    def test_anthropic_success(self, mock_anthropic_cls, mock_settings):
        mock_settings.return_value = _make_settings()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_anthropic_response("Anthropic response")

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
        mock_settings.return_value = _make_settings()

        mock_anthropic = MagicMock()
        mock_anthropic_cls.return_value = mock_anthropic
        mock_anthropic.messages.create.side_effect = Exception("Anthropic error")

        mock_ollama = MagicMock()
        mock_openai_cls.return_value = mock_ollama
        mock_ollama.chat.completions.create.return_value = _make_openai_response("Ollama response")

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient()
        result = client.chat("system prompt", "user prompt")

        assert result == "Ollama response"

    @patch("secondbrain.scripts.llm_client.get_settings")
    def test_no_anthropic_key_skips_to_ollama(self, mock_settings):
        mock_settings.return_value = _make_settings(anthropic_api_key=None)

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient()
        assert client.anthropic_client is None


class TestUsageType:
    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    def test_custom_usage_type_passed_to_log(self, mock_anthropic_cls, mock_settings):
        mock_settings.return_value = _make_settings()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_anthropic_response()

        mock_usage_store = MagicMock()

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient(usage_store=mock_usage_store, usage_type="extraction")
        client.chat("system", "user")

        mock_usage_store.log_usage.assert_called_once()
        call_args = mock_usage_store.log_usage.call_args
        assert call_args[0][2] == "extraction"  # usage_type is 3rd positional arg

    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    def test_default_usage_type_is_inbox(self, mock_anthropic_cls, mock_settings):
        mock_settings.return_value = _make_settings()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_anthropic_response()

        mock_usage_store = MagicMock()

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient(usage_store=mock_usage_store)
        client.chat("system", "user")

        mock_usage_store.log_usage.assert_called_once()
        call_args = mock_usage_store.log_usage.call_args
        assert call_args[0][2] == "inbox"


class TestTraceIdPropagation:
    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    def test_trace_id_passed_to_usage_store(self, mock_anthropic_cls, mock_settings):
        mock_settings.return_value = _make_settings()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_anthropic_response()

        mock_usage_store = MagicMock()

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient(usage_store=mock_usage_store)
        client.chat("system", "user", trace_id="trace-abc")

        mock_usage_store.log_usage.assert_called_once()
        kwargs = mock_usage_store.log_usage.call_args.kwargs
        assert kwargs["trace_id"] == "trace-abc"
        assert kwargs["latency_ms"] is not None
        assert kwargs["latency_ms"] > 0

    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    def test_no_trace_id_defaults_to_none(self, mock_anthropic_cls, mock_settings):
        mock_settings.return_value = _make_settings()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_anthropic_response()

        mock_usage_store = MagicMock()

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient(usage_store=mock_usage_store)
        client.chat("system", "user")

        kwargs = mock_usage_store.log_usage.call_args.kwargs
        assert kwargs["trace_id"] is None


class TestPerProviderFailureLogging:
    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    @patch("secondbrain.scripts.llm_client.OpenAI")
    def test_anthropic_fail_logs_error_then_ollama_success_logs_ok(
        self, mock_openai_cls, mock_anthropic_cls, mock_settings
    ):
        mock_settings.return_value = _make_settings()

        mock_anthropic = MagicMock()
        mock_anthropic_cls.return_value = mock_anthropic
        mock_anthropic.messages.create.side_effect = Exception("API timeout")

        mock_ollama = MagicMock()
        mock_openai_cls.return_value = mock_ollama
        mock_ollama.chat.completions.create.return_value = _make_openai_response("Ollama OK")

        mock_usage_store = MagicMock()

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient(usage_store=mock_usage_store)
        result = client.chat("system", "user", trace_id="t1")

        assert result == "Ollama OK"
        # Should have 2 log_usage calls: 1 error (anthropic) + 1 ok (ollama)
        assert mock_usage_store.log_usage.call_count == 2

        first_call = mock_usage_store.log_usage.call_args_list[0]
        assert first_call[0][0] == "anthropic"
        assert first_call.kwargs["status"] == "error"
        assert "API timeout" in first_call.kwargs["error_message"]
        assert first_call.kwargs["trace_id"] == "t1"

        second_call = mock_usage_store.log_usage.call_args_list[1]
        assert second_call[0][0] == "ollama"
        assert second_call.kwargs["status"] == "ok"
        assert second_call.kwargs["trace_id"] == "t1"

    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    def test_success_on_first_try_logs_single_ok(self, mock_anthropic_cls, mock_settings):
        mock_settings.return_value = _make_settings()
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_anthropic_response("Great")

        mock_usage_store = MagicMock()

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient(usage_store=mock_usage_store)
        client.chat("system", "user", trace_id="t2")

        assert mock_usage_store.log_usage.call_count == 1
        call = mock_usage_store.log_usage.call_args
        assert call.kwargs["status"] == "ok"
        assert call.kwargs["latency_ms"] > 0
