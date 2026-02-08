"""LLM-based answer generation with citations."""

from collections.abc import Iterator
from typing import Any

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
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        """Initialize the answerer.

        Args:
            model: OpenAI model to use for generation.
            api_key: OpenAI API key.
            base_url: Custom API base URL (e.g. Ollama's OpenAI-compatible endpoint).
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Lazy-load the OpenAI client."""
        if self._client is None:
            api_key = self.api_key
            if self.base_url and not api_key:
                api_key = "ollama"
            self._client = OpenAI(
                api_key=api_key,
                base_url=self.base_url,
            )
        return self._client

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

        # Build messages
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        # Add sources as system context
        messages.append(
            {
                "role": "system",
                "content": f"SOURCES FROM USER'S NOTES:\n\n{context}",
            }
        )

        # Add conversation history
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages
                messages.append({"role": msg.role, "content": msg.content})

        # Add current query
        messages.append({"role": "user", "content": query})

        # Generate answer
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.3,
            max_tokens=1000,
        )

        return response.choices[0].message.content or ""

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

        # Build messages
        messages: list[dict[str, Any]] = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        messages.append(
            {
                "role": "system",
                "content": f"SOURCES FROM USER'S NOTES:\n\n{context}",
            }
        )

        if conversation_history:
            for msg in conversation_history[-10:]:
                messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": query})

        # Generate streaming answer
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.3,
            max_tokens=1000,
            stream=True,
        )

        for chunk in stream:
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
