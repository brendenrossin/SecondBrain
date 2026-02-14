"""LLM-based reranker for improving retrieval precision."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from anthropic import Anthropic
from openai import OpenAI

from secondbrain.models import RetrievalLabel
from secondbrain.retrieval.hybrid import RetrievalCandidate

if TYPE_CHECKING:
    from secondbrain.stores.usage import UsageStore

logger = logging.getLogger(__name__)


@dataclass
class RankedCandidate:
    """A candidate with rerank score."""

    candidate: RetrievalCandidate
    rerank_score: float


class LLMReranker:
    """LLM-based reranker using Anthropic or OpenAI API."""

    SYSTEM_PROMPT = """You are a relevance scorer. Given a query and multiple text chunks from a personal knowledge base, rate how relevant each chunk is to answering the query.

Each chunk includes metadata: the vault folder it's from (e.g. 00_Daily, 10_Notes, 20_Projects) and optionally a date. Use dates to assess relevance for temporal queries (e.g. "yesterday", "this week", "recent").

Score from 0-10:
- 0-2: Not relevant at all
- 3-4: Tangentially related but doesn't help answer the query
- 5-6: Somewhat relevant, provides some useful context
- 7-8: Relevant, directly addresses part of the query
- 9-10: Highly relevant, directly and completely addresses the query

Respond with ONLY a JSON array of scores in order, e.g.: [8.5, 3.0, 7.0, ...]
The array MUST have exactly the same number of elements as chunks provided."""

    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        api_key: str | None = None,
        base_url: str | None = None,
        provider: str = "anthropic",
        rerank_threshold: float = 5.0,
        hallucination_threshold: float = 3.0,
        usage_store: UsageStore | None = None,
    ) -> None:
        """Initialize the reranker.

        Args:
            model: Model to use for reranking.
            api_key: API key.
            base_url: Custom API base URL (e.g. Ollama's OpenAI-compatible endpoint).
            provider: "anthropic" or "openai" (Ollama uses "openai" with base_url).
            rerank_threshold: Minimum rerank score to consider relevant.
            hallucination_threshold: If similarity is high but rerank is below this,
                flag as potential hallucination.
            usage_store: Optional usage store for cost tracking.
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.provider = provider
        self.rerank_threshold = rerank_threshold
        self.hallucination_threshold = hallucination_threshold
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

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        top_n: int = 5,
    ) -> tuple[list[RankedCandidate], RetrievalLabel]:
        """Rerank candidates using LLM scoring.

        Args:
            query: The search query.
            candidates: List of candidates from retrieval.
            top_n: Number of top candidates to return.

        Returns:
            Tuple of (ranked_candidates, retrieval_label).
        """
        if not candidates:
            return [], RetrievalLabel.NO_RESULTS

        # Score all candidates in a single batch API call
        scores = self._score_candidates_batch(query, candidates)

        # Build ranked list
        ranked: list[RankedCandidate] = []
        has_hallucination_risk = False

        for candidate, score in zip(candidates, scores, strict=True):
            # Check for hallucination risk
            if candidate.similarity_score > 0.7 and score < self.hallucination_threshold:
                has_hallucination_risk = True

            ranked.append(RankedCandidate(candidate=candidate, rerank_score=score))

        # Sort by rerank score
        ranked.sort(key=lambda r: r.rerank_score, reverse=True)

        # Take top_n
        top_ranked = ranked[:top_n]

        # Determine label
        if not top_ranked:
            label = RetrievalLabel.NO_RESULTS
        elif has_hallucination_risk:
            label = RetrievalLabel.HALLUCINATION_RISK
        elif all(r.rerank_score < self.rerank_threshold for r in top_ranked):
            label = RetrievalLabel.IRRELEVANT
        else:
            label = RetrievalLabel.PASS

        return top_ranked, label

    def _score_candidates_batch(
        self, query: str, candidates: list[RetrievalCandidate]
    ) -> list[float]:
        """Score all candidates in a single API call."""
        # Build chunks text
        chunks_text = []
        for i, candidate in enumerate(candidates):
            context = f"[{i + 1}]"
            if candidate.note_folder:
                context += f" [{candidate.note_folder}]"
            if candidate.note_date:
                context += f" ({candidate.note_date})"
            context += f" {candidate.note_title}"
            if candidate.heading_path:
                context += f" > {' > '.join(candidate.heading_path)}"
            context += f"\n{candidate.chunk_text[:500]}"
            chunks_text.append(context)

        all_chunks = "\n\n---\n\n".join(chunks_text)
        user_content = f"Query: {query}\n\nChunks:\n\n{all_chunks}"

        try:
            if self.provider == "anthropic":
                response = self.anthropic_client.messages.create(
                    model=self.model,
                    max_tokens=200,
                    system=self.SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_content}],
                )
                content = response.content[0].text  # type: ignore[union-attr]
                self._log_usage(
                    "anthropic",
                    self.model,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
            else:
                oai_response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0,
                    max_tokens=200,
                )
                content = oai_response.choices[0].message.content or "[]"
                if oai_response.usage:
                    provider_name = "ollama" if self.base_url else "openai"
                    self._log_usage(
                        provider_name,
                        self.model,
                        oai_response.usage.prompt_tokens,
                        oai_response.usage.completion_tokens,
                    )

            # Parse scores from JSON array
            try:
                scores = json.loads(content)
                if isinstance(scores, list) and len(scores) == len(candidates):
                    return [float(s) for s in scores]
            except (json.JSONDecodeError, ValueError):
                pass

            # Try to extract numbers from response
            numbers = re.findall(r"\b(\d+(?:\.\d+)?)\b", content)
            if len(numbers) >= len(candidates):
                return [float(n) for n in numbers[: len(candidates)]]

            # Fall back to similarity scores
            return [c.similarity_score * 10 for c in candidates]

        except Exception as e:
            logger.warning("Batch reranking error: %s", e)
            # Fall back to similarity scores
            return [c.similarity_score * 10 for c in candidates]

    def _log_usage(self, provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
        if self._usage_store:
            from secondbrain.stores.usage import calculate_cost

            cost = calculate_cost(provider, model, input_tokens, output_tokens)
            self._usage_store.log_usage(
                provider, model, "chat_rerank", input_tokens, output_tokens, cost
            )
