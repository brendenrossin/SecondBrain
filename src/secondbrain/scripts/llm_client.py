"""Shared LLM client with Anthropic-first, Ollama, OpenAI-fallback strategy."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from anthropic import Anthropic
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from secondbrain.config import get_settings

if TYPE_CHECKING:
    from secondbrain.stores.usage import UsageStore

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM client that tries Anthropic first, falls back to Ollama then OpenAI."""

    def __init__(self, usage_store: UsageStore | None = None, usage_type: str = "inbox") -> None:
        self._anthropic_client: Anthropic | None = None
        self._ollama_client: OpenAI | None = None
        self._openai_client: OpenAI | None = None
        self._settings = get_settings()
        self.model_name: str = self._settings.inbox_model
        self._usage_store = usage_store
        self._usage_type = usage_type

    @property
    def anthropic_client(self) -> Anthropic | None:
        """Lazy-load Anthropic client (None if no API key)."""
        if self._anthropic_client is None and self._settings.anthropic_api_key:
            self._anthropic_client = Anthropic(api_key=self._settings.anthropic_api_key)
        return self._anthropic_client

    @property
    def ollama_client(self) -> OpenAI:
        """Lazy-load Ollama client."""
        if self._ollama_client is None:
            self._ollama_client = OpenAI(
                base_url=self._settings.ollama_base_url,
                api_key="ollama",
            )
        return self._ollama_client

    @property
    def openai_client(self) -> OpenAI | None:
        """Lazy-load OpenAI client (None if no API key)."""
        if self._openai_client is None and self._settings.openai_api_key:
            self._openai_client = OpenAI(api_key=self._settings.openai_api_key)
        return self._openai_client

    def chat(self, system_prompt: str, user_prompt: str, trace_id: str | None = None) -> str:
        """Send a chat completion, trying Anthropic first then Ollama then OpenAI.

        Returns the assistant's response text.
        """
        # Try Anthropic first
        if self.anthropic_client:
            start = time.perf_counter()
            try:
                logger.info("Trying Anthropic (%s)...", self._settings.inbox_model)
                response = self.anthropic_client.messages.create(
                    model=self._settings.inbox_model,
                    max_tokens=2000,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                content = response.content[0].text  # type: ignore[union-attr]
                logger.info("Anthropic responded successfully")
                self._log_usage(
                    "anthropic",
                    self._settings.inbox_model,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    trace_id=trace_id,
                    latency_ms=(time.perf_counter() - start) * 1000,
                )
                return content
            except Exception as e:
                latency_ms = (time.perf_counter() - start) * 1000
                logger.warning("Anthropic failed, trying Ollama fallback...", exc_info=True)
                self._log_usage(
                    "anthropic",
                    self._settings.inbox_model,
                    0,
                    0,
                    trace_id=trace_id,
                    latency_ms=latency_ms,
                    status="error",
                    error_message=str(e)[:500],
                )

        # Try Ollama
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        start = time.perf_counter()
        try:
            logger.info("Trying Ollama (%s)...", self._settings.ollama_model)
            oai_response = self.ollama_client.chat.completions.create(
                model=self._settings.ollama_model,
                messages=messages,
                temperature=0.2,
                max_tokens=2000,
            )
            content = oai_response.choices[0].message.content or ""
            logger.info("Ollama responded successfully")
            input_tok = oai_response.usage.prompt_tokens if oai_response.usage else 0
            output_tok = oai_response.usage.completion_tokens if oai_response.usage else 0
            self._log_usage(
                "ollama",
                self._settings.ollama_model,
                input_tok,
                output_tok,
                trace_id=trace_id,
                latency_ms=(time.perf_counter() - start) * 1000,
            )
            return content
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("Ollama failed, trying OpenAI fallback...", exc_info=True)
            self._log_usage(
                "ollama",
                self._settings.ollama_model,
                0,
                0,
                trace_id=trace_id,
                latency_ms=latency_ms,
                status="error",
                error_message=str(e)[:500],
            )

        # Fallback to OpenAI
        if self.openai_client:
            start = time.perf_counter()
            try:
                oai_response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.2,
                    max_tokens=2000,
                )
                content = oai_response.choices[0].message.content or ""
                logger.info("OpenAI responded successfully")
                input_tok = oai_response.usage.prompt_tokens if oai_response.usage else 0
                output_tok = oai_response.usage.completion_tokens if oai_response.usage else 0
                self._log_usage(
                    "openai",
                    "gpt-4o-mini",
                    input_tok,
                    output_tok,
                    trace_id=trace_id,
                    latency_ms=(time.perf_counter() - start) * 1000,
                )
                return content
            except Exception as e:
                latency_ms = (time.perf_counter() - start) * 1000
                logger.error("OpenAI also failed", exc_info=True)
                self._log_usage(
                    "openai",
                    "gpt-4o-mini",
                    0,
                    0,
                    trace_id=trace_id,
                    latency_ms=latency_ms,
                    status="error",
                    error_message=str(e)[:500],
                )

        raise RuntimeError("All LLM providers failed (Anthropic, Ollama, OpenAI)")

    def _log_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        trace_id: str | None = None,
        latency_ms: float | None = None,
        status: str = "ok",
        error_message: str | None = None,
    ) -> None:
        if self._usage_store:
            from secondbrain.stores.usage import calculate_cost

            cost = calculate_cost(provider, model, input_tokens, output_tokens)
            self._usage_store.log_usage(
                provider,
                model,
                self._usage_type,
                input_tokens,
                output_tokens,
                cost,
                trace_id=trace_id,
                latency_ms=latency_ms,
                status=status,
                error_message=error_message,
            )

    def chat_json(
        self, system_prompt: str, user_prompt: str, trace_id: str | None = None
    ) -> dict[str, Any]:
        """Send a chat completion and parse the response as JSON.

        The system prompt should instruct the model to return valid JSON.
        """
        raw = self.chat(system_prompt, user_prompt, trace_id=trace_id)

        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove first line (```json or ```) and last line (```)
            lines = cleaned.split("\n")
            lines = lines[1:]  # remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        result: dict[str, Any] = json.loads(cleaned)
        return result
