"""Tests for the LLM client with Anthropic provider support."""

from unittest.mock import MagicMock, patch

import pytest


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


class TestAllProvidersFail:
    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    @patch("secondbrain.scripts.llm_client.OpenAI")
    def test_raises_runtime_error_when_all_fail(
        self, mock_openai_cls, mock_anthropic_cls, mock_settings
    ):
        mock_settings.return_value = _make_settings(openai_api_key="test-openai-key")

        mock_anthropic = MagicMock()
        mock_anthropic_cls.return_value = mock_anthropic
        mock_anthropic.messages.create.side_effect = Exception("Anthropic down")

        mock_ollama = MagicMock()
        mock_openai = MagicMock()
        # OpenAI constructor is called twice: once for Ollama, once for OpenAI
        mock_openai_cls.side_effect = [mock_ollama, mock_openai]
        mock_ollama.chat.completions.create.side_effect = Exception("Ollama down")
        mock_openai.chat.completions.create.side_effect = Exception("OpenAI down")

        mock_usage_store = MagicMock()

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient(usage_store=mock_usage_store)

        with pytest.raises(RuntimeError, match="All LLM providers failed"):
            client.chat("system", "user", trace_id="fail-all")

        # Should have 3 error logs: anthropic, ollama, openai
        assert mock_usage_store.log_usage.call_count == 3
        providers = [c[0][0] for c in mock_usage_store.log_usage.call_args_list]
        assert providers == ["anthropic", "ollama", "openai"]
        for c in mock_usage_store.log_usage.call_args_list:
            assert c.kwargs["status"] == "error"
            assert c.kwargs["trace_id"] == "fail-all"

    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    @patch("secondbrain.scripts.llm_client.OpenAI")
    def test_raises_when_no_openai_key_and_others_fail(
        self, mock_openai_cls, mock_anthropic_cls, mock_settings
    ):
        mock_settings.return_value = _make_settings(openai_api_key=None)

        mock_anthropic = MagicMock()
        mock_anthropic_cls.return_value = mock_anthropic
        mock_anthropic.messages.create.side_effect = Exception("Anthropic down")

        mock_ollama = MagicMock()
        mock_openai_cls.return_value = mock_ollama
        mock_ollama.chat.completions.create.side_effect = Exception("Ollama down")

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient()

        with pytest.raises(RuntimeError, match="All LLM providers failed"):
            client.chat("system", "user")

    @patch("secondbrain.scripts.llm_client.get_settings")
    @patch("secondbrain.scripts.llm_client.Anthropic")
    @patch("secondbrain.scripts.llm_client.OpenAI")
    def test_openai_fallback_uses_class_constant_model(
        self, mock_openai_cls, mock_anthropic_cls, mock_settings
    ):
        mock_settings.return_value = _make_settings(openai_api_key="test-key")

        mock_anthropic = MagicMock()
        mock_anthropic_cls.return_value = mock_anthropic
        mock_anthropic.messages.create.side_effect = Exception("fail")

        mock_ollama = MagicMock()
        mock_openai = MagicMock()
        mock_openai_cls.side_effect = [mock_ollama, mock_openai]
        mock_ollama.chat.completions.create.side_effect = Exception("fail")
        mock_openai.chat.completions.create.return_value = _make_openai_response("OK")

        from secondbrain.scripts.llm_client import LLMClient

        client = LLMClient()
        client.chat("system", "user")

        # Verify the OpenAI fallback used the class constant
        call_kwargs = mock_openai.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == LLMClient.OPENAI_FALLBACK_MODEL
