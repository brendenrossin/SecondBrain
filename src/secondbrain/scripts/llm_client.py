"""Shared LLM client with Ollama-first, OpenAI-fallback strategy."""

import json
import logging
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from secondbrain.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM client that tries Ollama first, falls back to OpenAI."""

    def __init__(self) -> None:
        self._ollama_client: OpenAI | None = None
        self._openai_client: OpenAI | None = None
        self._settings = get_settings()
        self.model_name: str = self._settings.ollama_model

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

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat completion, trying Ollama first then OpenAI.

        Returns the assistant's response text.
        """
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Try Ollama first
        try:
            logger.info("Trying Ollama (%s)...", self._settings.ollama_model)
            response = self.ollama_client.chat.completions.create(
                model=self._settings.ollama_model,
                messages=messages,
                temperature=0.2,
                max_tokens=2000,
            )
            content = response.choices[0].message.content or ""
            logger.info("Ollama responded successfully")
            return content
        except Exception:
            logger.warning("Ollama failed, trying OpenAI fallback...", exc_info=True)

        # Fallback to OpenAI
        if self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.2,
                    max_tokens=2000,
                )
                content = response.choices[0].message.content or ""
                logger.info("OpenAI responded successfully")
                return content
            except Exception:
                logger.error("OpenAI also failed", exc_info=True)

        raise RuntimeError("Both Ollama and OpenAI LLM calls failed")

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Send a chat completion and parse the response as JSON.

        The system prompt should instruct the model to return valid JSON.
        """
        raw = self.chat(system_prompt, user_prompt)

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
