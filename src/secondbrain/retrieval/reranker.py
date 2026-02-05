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

    SYSTEM_PROMPT = """You are a relevance scorer. Given a query and a text chunk from a personal knowledge base, rate how relevant the chunk is to answering the query.

Score from 0-10:
- 0-2: Not relevant at all
- 3-4: Tangentially related but doesn't help answer the query
- 5-6: Somewhat relevant, provides some useful context
- 7-8: Relevant, directly addresses part of the query
- 9-10: Highly relevant, directly and completely addresses the query

Respond with ONLY a JSON object: {"score": <number>, "reason": "<brief explanation>"}"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        rerank_threshold: float = 5.0,
        hallucination_threshold: float = 3.0,
    ) -> None:
        """Initialize the reranker.

        Args:
            model: OpenAI model to use for reranking.
            rerank_threshold: Minimum rerank score to consider relevant.
            hallucination_threshold: If similarity is high but rerank is below this,
                flag as potential hallucination.
        """
        self.model = model
        self.rerank_threshold = rerank_threshold
        self.hallucination_threshold = hallucination_threshold
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Lazy-load the OpenAI client."""
        if self._client is None:
            self._client = OpenAI()
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

        # Score each candidate
        ranked: list[RankedCandidate] = []
        has_hallucination_risk = False

        for candidate in candidates:
            score = self._score_candidate(query, candidate)

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

    def _score_candidate(self, query: str, candidate: RetrievalCandidate) -> float:
        """Score a single candidate."""
        # Build context
        context = f"Note: {candidate.note_title}"
        if candidate.heading_path:
            context += f" > {' > '.join(candidate.heading_path)}"
        context += f"\n\n{candidate.chunk_text}"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Query: {query}\n\nChunk:\n{context}",
                    },
                ],
                temperature=0,
                max_tokens=100,
            )

            content = response.choices[0].message.content or "{}"

            # Parse score from JSON response
            try:
                result = json.loads(content)
                return float(result.get("score", 0))
            except (json.JSONDecodeError, ValueError):
                # Try to extract number from response
                match = re.search(r"\b(\d+(?:\.\d+)?)\b", content)
                if match:
                    return float(match.group(1))
                return 0.0

        except Exception as e:
            print(f"Reranking error: {e}")
            # Fall back to similarity score scaled to 0-10
            return candidate.similarity_score * 10
