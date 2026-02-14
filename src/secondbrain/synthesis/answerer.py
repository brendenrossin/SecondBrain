"""LLM-based answer generation with citations."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from anthropic import Anthropic
from openai import OpenAI

from secondbrain.models import ConversationMessage, RetrievalLabel
from secondbrain.retrieval.link_expander import LinkedContext
from secondbrain.retrieval.reranker import RankedCandidate

if TYPE_CHECKING:
    from secondbrain.stores.usage import UsageStore

logger = logging.getLogger(__name__)


class Answerer:
    """Generates answers using LLM with grounding in retrieved chunks."""

    SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on the user's personal notes. You have access to relevant excerpts from their knowledge base.

IMPORTANT RULES:
1. ONLY use information from the provided sources to answer questions
2. If the sources don't contain enough information to answer, say so clearly
3. Be concise and direct in your answers
4. When referencing information, you may mention which note it came from
5. Do not make up information that isn't in the sources
6. If asked to brainstorm or speculate, you may do so but clearly label it as speculation
7. Sources include dates and folder context. Use dates to answer temporal queries like "yesterday", "this week", "most recent", etc.
8. You also have access to connected notes that are explicitly linked from the retrieved sources. Use them for additional context when relevant.

The user's relevant notes are provided below."""

    NO_RESULTS_RESPONSE = """I couldn't find any relevant information in your notes to answer this question.

You might want to:
- Rephrase your question with different keywords
- Check if you have notes on this topic
- Ask me to brainstorm (I'll make it clear when I'm speculating)"""

    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        api_key: str | None = None,
        base_url: str | None = None,
        provider: str = "anthropic",
        usage_store: UsageStore | None = None,
    ) -> None:
        """Initialize the answerer.

        Args:
            model: Model to use for generation.
            api_key: API key.
            base_url: Custom API base URL (e.g. Ollama's OpenAI-compatible endpoint).
            provider: "anthropic" or "openai" (Ollama uses "openai" with base_url).
            usage_store: Optional usage store for cost tracking.
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.provider = provider
        self._usage_store = usage_store
        self._openai_client: OpenAI | None = None
        self._anthropic_client: Anthropic | None = None

    @property
    def openai_client(self) -> OpenAI:
        """Lazy-load the OpenAI client."""
        if self._openai_client is None:
            api_key = self.api_key
            if self.base_url and not api_key:
                api_key = "ollama"
            self._openai_client = OpenAI(
                api_key=api_key,
                base_url=self.base_url,
                timeout=60.0,
            )
        return self._openai_client

    @property
    def anthropic_client(self) -> Anthropic:
        """Lazy-load the Anthropic client."""
        if self._anthropic_client is None:
            self._anthropic_client = Anthropic(
                api_key=self.api_key,
                timeout=60.0,
            )
        return self._anthropic_client

    def answer(
        self,
        query: str,
        ranked_candidates: list[RankedCandidate],
        retrieval_label: RetrievalLabel,
        conversation_history: list[ConversationMessage] | None = None,
        linked_context: list[LinkedContext] | None = None,
    ) -> str:
        """Generate an answer based on retrieved chunks.

        Args:
            query: The user's query.
            ranked_candidates: Ranked retrieval candidates.
            retrieval_label: The retrieval evaluation label.
            conversation_history: Optional conversation history.
            linked_context: Optional linked notes from wiki link expansion.

        Returns:
            The generated answer.
        """
        # Handle no results case
        if retrieval_label == RetrievalLabel.NO_RESULTS or not ranked_candidates:
            return self.NO_RESULTS_RESPONSE

        # Build context from candidates
        context = self._build_context(ranked_candidates, linked_context)

        if self.provider == "anthropic":
            # Anthropic: system is a separate param, not a message
            system_text = self.SYSTEM_PROMPT + f"\n\nSOURCES FROM USER'S NOTES:\n\n{context}"
            messages: list[dict[str, Any]] = []
            if conversation_history:
                for msg in conversation_history[-10:]:
                    messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": query})

            response = self.anthropic_client.messages.create(
                model=self.model,
                max_tokens=1000,
                system=system_text,
                messages=messages,  # type: ignore[arg-type]
            )
            self._log_usage(
                "anthropic",
                self.model,
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            return response.content[0].text  # type: ignore[union-attr]
        else:
            # OpenAI / Ollama path
            oai_messages: list[dict[str, Any]] = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "system", "content": f"SOURCES FROM USER'S NOTES:\n\n{context}"},
            ]
            if conversation_history:
                for msg in conversation_history[-10:]:
                    oai_messages.append({"role": msg.role, "content": msg.content})
            oai_messages.append({"role": "user", "content": query})

            oai_response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=oai_messages,  # type: ignore[arg-type]
                temperature=0.3,
                max_tokens=1000,
            )
            if oai_response.usage:
                provider_name = "ollama" if self.base_url else "openai"
                self._log_usage(
                    provider_name,
                    self.model,
                    oai_response.usage.prompt_tokens,
                    oai_response.usage.completion_tokens,
                )
            return oai_response.choices[0].message.content or ""

    def answer_stream(
        self,
        query: str,
        ranked_candidates: list[RankedCandidate],
        retrieval_label: RetrievalLabel,
        conversation_history: list[ConversationMessage] | None = None,
        linked_context: list[LinkedContext] | None = None,
    ) -> Iterator[str]:
        """Generate a streaming answer based on retrieved chunks.

        Args:
            query: The user's query.
            ranked_candidates: Ranked retrieval candidates.
            retrieval_label: The retrieval evaluation label.
            conversation_history: Optional conversation history.
            linked_context: Optional linked notes from wiki link expansion.

        Yields:
            Answer tokens as they're generated.
        """
        # Handle no results case
        if retrieval_label == RetrievalLabel.NO_RESULTS or not ranked_candidates:
            yield self.NO_RESULTS_RESPONSE
            return

        # Build context from candidates
        context = self._build_context(ranked_candidates, linked_context)

        if self.provider == "anthropic":
            system_text = self.SYSTEM_PROMPT + f"\n\nSOURCES FROM USER'S NOTES:\n\n{context}"
            messages: list[dict[str, Any]] = []
            if conversation_history:
                for msg in conversation_history[-10:]:
                    messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": query})

            with self.anthropic_client.messages.stream(
                model=self.model,
                max_tokens=1000,
                system=system_text,
                messages=messages,  # type: ignore[arg-type]
            ) as stream:
                yield from stream.text_stream
                # After stream completes, log usage from the final message
                final = stream.get_final_message()
                self._log_usage(
                    "anthropic",
                    self.model,
                    final.usage.input_tokens,
                    final.usage.output_tokens,
                )
        else:
            # OpenAI / Ollama path
            oai_messages: list[dict[str, Any]] = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "system", "content": f"SOURCES FROM USER'S NOTES:\n\n{context}"},
            ]
            if conversation_history:
                for msg in conversation_history[-10:]:
                    oai_messages.append({"role": msg.role, "content": msg.content})
            oai_messages.append({"role": "user", "content": query})

            # Request usage stats in the final stream chunk (OpenAI supports this;
            # Ollama may ignore it, which is fine)
            stream_kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": oai_messages,
                "temperature": 0.3,
                "max_tokens": 1000,
                "stream": True,
            }
            if not self.base_url:
                stream_kwargs["stream_options"] = {"include_usage": True}

            oai_stream = self.openai_client.chat.completions.create(**stream_kwargs)

            stream_usage = None
            for chunk in oai_stream:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta_content = chunk.choices[0].delta.content
                    if delta_content:
                        yield delta_content
                # Capture usage from the final chunk (OpenAI includes it there)
                if hasattr(chunk, "usage") and chunk.usage:
                    stream_usage = chunk.usage

            if stream_usage:
                provider_name = "ollama" if self.base_url else "openai"
                self._log_usage(
                    provider_name,
                    self.model,
                    stream_usage.prompt_tokens,
                    stream_usage.completion_tokens,
                )

    def _log_usage(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
        if self._usage_store:
            from secondbrain.stores.usage import calculate_cost

            cost = calculate_cost(provider, model, input_tokens, output_tokens)
            self._usage_store.log_usage(
                provider, model, "chat_answer", input_tokens, output_tokens, cost
            )

    def _build_context(
        self,
        ranked_candidates: list[RankedCandidate],
        linked_context: list[LinkedContext] | None = None,
    ) -> str:
        """Build context string from ranked candidates and optional linked notes."""
        context_parts = []

        for i, rc in enumerate(ranked_candidates, 1):
            candidate = rc.candidate
            header = f"[{i}]"
            if candidate.note_folder:
                header += f" [{candidate.note_folder}]"
            if candidate.note_date:
                header += f" ({candidate.note_date})"
            header += f" {candidate.note_title}"
            if candidate.heading_path:
                header += f" > {' > '.join(candidate.heading_path)}"

            context_parts.append(f"{header}\n{candidate.chunk_text}")

        result = "\n\n---\n\n".join(context_parts)

        if linked_context:
            linked_parts = []
            for i, lc in enumerate(linked_context, 1):
                # Extract folder from note_path
                folder = lc.note_path.split("/")[0] if "/" in lc.note_path else ""
                header = f"[C{i}]"
                if folder:
                    header += f" [{folder}]"
                header += f" {lc.note_title} (linked from: {lc.linked_from})"
                linked_parts.append(f"{header}\n{lc.chunk_text}")

            result += "\n\n---\n\nCONNECTED NOTES (linked from retrieved results):\n\n"
            result += "\n\n".join(linked_parts)

        return result
