"""Retrieval evaluation metrics: Recall@K, Precision@K, MRR."""


def recall_at_k(expected: list[str], retrieved: list[str], k: int) -> float:
    """Fraction of expected notes that appear in the top-K retrieved results.

    Args:
        expected: List of expected note paths.
        retrieved: List of retrieved note paths (ranked).
        k: Number of top results to consider.

    Returns:
        Recall score between 0.0 and 1.0.
    """
    if not expected:
        return 1.0
    top_k = set(retrieved[:k])
    hits = sum(1 for e in expected if e in top_k)
    return hits / len(expected)


def precision_at_k(expected: list[str], retrieved: list[str], k: int) -> float:
    """Fraction of top-K retrieved results that are in the expected set.

    Args:
        expected: List of expected note paths.
        retrieved: List of retrieved note paths (ranked).
        k: Number of top results to consider.

    Returns:
        Precision score between 0.0 and 1.0.
    """
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    expected_set = set(expected)
    hits = sum(1 for r in top_k if r in expected_set)
    return hits / len(top_k)


def mrr(expected: list[str], retrieved: list[str]) -> float:
    """Mean Reciprocal Rank: 1/rank of the first relevant result.

    Args:
        expected: List of expected note paths.
        retrieved: List of retrieved note paths (ranked).

    Returns:
        Reciprocal rank (0.0 if no relevant result found).
    """
    expected_set = set(expected)
    for i, r in enumerate(retrieved):
        if r in expected_set:
            return 1.0 / (i + 1)
    return 0.0
