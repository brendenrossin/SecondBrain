"""LLM-based answer generation with citations."""

from collections.abc import Iterator
from typing import Any

from anthropic import Anthropic
from openai import OpenAI

from secondbrain.models import ConversationMessage, RetrievalLabel
from secondbrain.retrieval.reranker import RankedCandidate


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

The user's relevant notes are provided below."""

    NO_RESULTS_RESPONSE = """I couldn't find any relevant information in your notes to answer this question.

You might want to:
- Rephrase your question with different keywords
- Check if you have notes on this topic
- Ask me to brainstorm (I'll make it clear when I'm speculating)"""

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20250929",
        api_key: str | None = None,
        base_url: str | None = None,
        provider: str = "anthropic",
    ) -> None:
        """Initialize the answerer.

        Args:
            model: Model to use for generation.
            api_key: API key.
            base_url: Custom API base URL (e.g. Ollama's OpenAI-compatible endpoint).
            provider: "anthropic" or "openai" (Ollama uses "openai" with base_url).
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.provider = provider
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
            )
        return self._openai_client

    @property
    def anthropic_client(self) -> Anthropic:
        """Lazy-load the Anthropic client."""
        if self._anthropic_client is None:
            self._anthropic_client = Anthropic(api_key=self.api_key)
        return self._anthropic_client

    def answer(
        self,
        query: str,
        ranked_candidates: list[RankedCandidate],
        retrieval_label: RetrievalLabel,
        conversation_history: list[ConversationMessage] | None = None,
    ) -> str:
        """Generate an answer based on retrieved chunks.

        Args:
            query: The user's query.
            ranked_candidates: Ranked retrieval candidates.
            retrieval_label: The retrieval evaluation label.
            conversation_history: Optional conversation history.

        Returns:
            The generated answer.
        """
        # Handle no results case
        if retrieval_label == RetrievalLabel.NO_RESULTS or not ranked_candidates:
            return self.NO_RESULTS_RESPONSE

        # Build context from candidates
        context = self._build_context(ranked_candidates)

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
            return oai_response.choices[0].message.content or ""

    def answer_stream(
        self,
        query: str,
        ranked_candidates: list[RankedCandidate],
        retrieval_label: RetrievalLabel,
        conversation_history: list[ConversationMessage] | None = None,
    ) -> Iterator[str]:
        """Generate a streaming answer based on retrieved chunks.

        Args:
            query: The user's query.
            ranked_candidates: Ranked retrieval candidates.
            retrieval_label: The retrieval evaluation label.
            conversation_history: Optional conversation history.

        Yields:
            Answer tokens as they're generated.
        """
        # Handle no results case
        if retrieval_label == RetrievalLabel.NO_RESULTS or not ranked_candidates:
            yield self.NO_RESULTS_RESPONSE
            return

        # Build context from candidates
        context = self._build_context(ranked_candidates)

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

            oai_stream = self.openai_client.chat.completions.create(
                model=self.model,
                messages=oai_messages,  # type: ignore[arg-type]
                temperature=0.3,
                max_tokens=1000,
                stream=True,
            )

            for chunk in oai_stream:
                if hasattr(chunk, "choices") and chunk.choices:  # type: ignore[union-attr]
                    delta_content = chunk.choices[0].delta.content  # type: ignore[union-attr]
                    if delta_content:
                        yield delta_content

    def _build_context(self, ranked_candidates: list[RankedCandidate]) -> str:
        """Build context string from ranked candidates."""
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

        return "\n\n---\n\n".join(context_parts)
