"""LLM-powered context blurb generation for contextual retrieval."""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from anthropic import Anthropic

if TYPE_CHECKING:
    from secondbrain.models import Chunk
    from secondbrain.stores.usage import UsageStore

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a context annotation assistant for a personal knowledge base. "
    "Given a document and a specific chunk from it, write a short (1-2 sentence) context blurb "
    "that situates this chunk within the document. Include the document topic, relevant section "
    "context, and any key entities that aren't in the chunk itself. Be concise and factual."
)


def _build_user_message(title: str, document: str, chunk: str) -> str:
    """Build user message for context generation.

    Uses string concatenation instead of str.format() to avoid KeyError
    when vault content contains {curly braces} (e.g. code blocks).
    """
    return (
        '<document title="'
        + title
        + '">\n'
        + document
        + "\n</document>\n\n<chunk>\n"
        + chunk
        + "\n</chunk>\n\n"
        + "Write a 1-2 sentence context blurb for this chunk."
    )


class ContextGenerator:
    """Generates context blurbs for chunks using Anthropic Haiku."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5",
        usage_store: UsageStore | None = None,
    ) -> None:
        self._client = Anthropic(api_key=api_key, timeout=60.0)
        self._model = model
        self._usage_store = usage_store

    def generate_blurbs(
        self,
        note_title: str,
        note_content: str,
        chunks: list[Chunk],
        trace_id: str | None = None,
    ) -> list[str]:
        """Generate context blurbs for a list of chunks.

        Returns a list of blurb strings aligned 1:1 with input chunks.
        On error for any chunk, returns empty string for that chunk.
        """
        if trace_id is None:
            trace_id = uuid.uuid4().hex

        blurbs: list[str] = []
        for chunk in chunks:
            blurb = self._generate_one(note_title, note_content, chunk, trace_id)
            blurbs.append(blurb)
        return blurbs

    def _generate_one(
        self,
        note_title: str,
        note_content: str,
        chunk: Chunk,
        trace_id: str,
    ) -> str:
        """Generate a single context blurb for one chunk."""
        start = time.time()
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=150,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": _build_user_message(note_title, note_content, chunk.chunk_text),
                    }
                ],
            )
            content_block = response.content[0]
            blurb = content_block.text.strip() if hasattr(content_block, "text") else ""
            latency_ms = (time.time() - start) * 1000
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            if self._usage_store:
                from secondbrain.stores.usage import calculate_cost

                self._usage_store.log_usage(
                    provider="anthropic",
                    model=self._model,
                    usage_type="context_generation",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=calculate_cost("anthropic", self._model, input_tokens, output_tokens),
                    trace_id=trace_id,
                    latency_ms=latency_ms,
                    status="ok",
                )

            return blurb

        except Exception:
            latency_ms = (time.time() - start) * 1000
            logger.warning(
                "Failed to generate context blurb for chunk %s",
                chunk.chunk_id,
                exc_info=True,
            )

            if self._usage_store:
                self._usage_store.log_usage(
                    provider="anthropic",
                    model=self._model,
                    usage_type="context_generation",
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    trace_id=trace_id,
                    latency_ms=latency_ms,
                    status="error",
                )

            return ""
