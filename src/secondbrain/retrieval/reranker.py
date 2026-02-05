"""LLM-based reranker for improving retrieval precision."""

import json
import re
from dataclasses import dataclass

from openai import OpenAI

from secondbrain.models import RetrievalLabel
from secondbrain.retrieval.hybrid import RetrievalCandidate


@dataclass
class RankedCandidate:
    """A candidate with rerank score."""

    candidate: RetrievalCandidate
    rerank_score: float


class LLMReranker:
    """LLM-based reranker using OpenAI API."""

    SYSTEM_PROMPT = """You are a relevance scorer. Given a query and multiple text chunks from a personal knowledge base, rate how relevant each chunk is to answering the query.

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
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
        rerank_threshold: float = 5.0,
        hallucination_threshold: float = 3.0,
    ) -> None:
        """Initialize the reranker.

        Args:
            model: OpenAI model to use for reranking.
            api_key: OpenAI API key.
            base_url: Custom API base URL (e.g. Ollama's OpenAI-compatible endpoint).
            rerank_threshold: Minimum rerank score to consider relevant.
            hallucination_threshold: If similarity is high but rerank is below this,
                flag as potential hallucination.
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.rerank_threshold = rerank_threshold
        self.hallucination_threshold = hallucination_threshold
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Lazy-load the OpenAI client."""
        if self._client is None:
            kwargs: dict[str, str] = {}
            if self.api_key:
                kwargs["api_key"] = self.api_key
            if self.base_url:
                kwargs["base_url"] = self.base_url
                kwargs.setdefault("api_key", "ollama")
            self._client = OpenAI(**kwargs)
        return self._client

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
            if (
                candidate.similarity_score > 0.7
                and score < self.hallucination_threshold
            ):
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
            context = f"[{i+1}] Note: {candidate.note_title}"
            if candidate.heading_path:
                context += f" > {' > '.join(candidate.heading_path)}"
            context += f"\n{candidate.chunk_text[:500]}"  # Truncate for efficiency
            chunks_text.append(context)

        all_chunks = "\n\n---\n\n".join(chunks_text)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Query: {query}\n\nChunks:\n\n{all_chunks}",
                    },
                ],
                temperature=0,
                max_tokens=200,
            )

            content = response.choices[0].message.content or "[]"

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
            print(f"Batch reranking error: {e}")
            # Fall back to similarity scores
            return [c.similarity_score * 10 for c in candidates]
