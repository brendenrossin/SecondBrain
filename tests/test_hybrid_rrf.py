"""Functional tests for retrieval/hybrid.py — RRF formula correctness and ranking logic."""

from unittest.mock import MagicMock

from secondbrain.retrieval.hybrid import HybridRetriever


def _make_retriever(
    vector_results: list[tuple] | None = None,
    lexical_results: list[tuple] | None = None,
    lexical_chunks: dict[str, dict] | None = None,
) -> HybridRetriever:
    """Build a HybridRetriever with controlled mock stores."""
    vector_store = MagicMock()
    lexical_store = MagicMock()
    embedder = MagicMock()

    embedder.embed_single.return_value = [0.1] * 384

    vector_store.search.return_value = vector_results or []
    lexical_store.search.return_value = lexical_results or []

    if lexical_chunks:
        lexical_store.get_chunk.side_effect = lambda cid: lexical_chunks.get(cid)
    else:
        lexical_store.get_chunk.return_value = None

    return HybridRetriever(
        vector_store=vector_store,
        lexical_store=lexical_store,
        embedder=embedder,
        rrf_k=60,
    )


class TestRRFScoreCalculation:
    """Tests that the RRF formula produces correct scores."""

    def test_chunk_in_both_sources_ranks_higher(self):
        """A chunk appearing in both vector and lexical results should score higher."""
        # chunk_a in both, chunk_b only in vector, chunk_c only in lexical
        vector_results = [
            (
                "chunk_a",
                0.9,
                {
                    "note_path": "a.md",
                    "note_title": "A",
                    "heading_path": "",
                    "note_folder": "",
                    "note_date": "",
                },
                "text a",
            ),
            (
                "chunk_b",
                0.8,
                {
                    "note_path": "b.md",
                    "note_title": "B",
                    "heading_path": "",
                    "note_folder": "",
                    "note_date": "",
                },
                "text b",
            ),
        ]
        lexical_results = [
            ("chunk_a", 5.0),
            ("chunk_c", 4.0),
        ]
        lexical_chunks = {
            "chunk_c": {
                "chunk_text": "text c",
                "note_path": "c.md",
                "note_title": "C",
                "heading_path": "",
                "note_folder": "",
                "note_date": "",
            }
        }

        retriever = _make_retriever(vector_results, lexical_results, lexical_chunks)
        candidates = retriever.retrieve("test query", top_k=10)

        scores = {c.chunk_id: c.rrf_score for c in candidates}
        # chunk_a should have highest RRF (in both sources)
        assert scores["chunk_a"] > scores["chunk_b"]
        assert scores["chunk_a"] > scores["chunk_c"]

    def test_rrf_formula_values(self):
        """Verify the exact RRF formula: 1/(k+rank) for each source."""
        # chunk_a: rank 1 in vector, rank 1 in lexical
        # RRF = 1/(60+1) + 1/(60+1) = 2/61
        vector_results = [
            (
                "chunk_a",
                0.9,
                {
                    "note_path": "a.md",
                    "note_title": "A",
                    "heading_path": "",
                    "note_folder": "",
                    "note_date": "",
                },
                "text",
            ),
        ]
        lexical_results = [
            ("chunk_a", 5.0),
        ]

        retriever = _make_retriever(vector_results, lexical_results)
        candidates = retriever.retrieve("test", top_k=10)

        assert len(candidates) == 1
        expected_rrf = 1.0 / (60 + 1) + 1.0 / (60 + 1)
        assert abs(candidates[0].rrf_score - expected_rrf) < 1e-10

    def test_single_source_rrf(self):
        """Chunk in only one source gets 1/(k+rank) from that source only."""
        vector_results = [
            (
                "chunk_a",
                0.9,
                {
                    "note_path": "a.md",
                    "note_title": "A",
                    "heading_path": "",
                    "note_folder": "",
                    "note_date": "",
                },
                "text",
            ),
        ]

        retriever = _make_retriever(vector_results, [])
        candidates = retriever.retrieve("test", top_k=10)

        expected_rrf = 1.0 / (60 + 1)
        assert abs(candidates[0].rrf_score - expected_rrf) < 1e-10

    def test_empty_query_returns_empty(self):
        retriever = _make_retriever([], [])
        candidates = retriever.retrieve("", top_k=10)
        assert candidates == []


class TestRankOrdering:
    """Tests that candidates are returned in RRF score order."""

    def test_results_sorted_by_rrf_descending(self):
        vector_results = [
            (
                "a",
                0.9,
                {
                    "note_path": "a.md",
                    "note_title": "A",
                    "heading_path": "",
                    "note_folder": "",
                    "note_date": "",
                },
                "text a",
            ),
            (
                "b",
                0.7,
                {
                    "note_path": "b.md",
                    "note_title": "B",
                    "heading_path": "",
                    "note_folder": "",
                    "note_date": "",
                },
                "text b",
            ),
            (
                "c",
                0.5,
                {
                    "note_path": "c.md",
                    "note_title": "C",
                    "heading_path": "",
                    "note_folder": "",
                    "note_date": "",
                },
                "text c",
            ),
        ]

        retriever = _make_retriever(vector_results, [])
        candidates = retriever.retrieve("test", top_k=10)

        rrf_scores = [c.rrf_score for c in candidates]
        assert rrf_scores == sorted(rrf_scores, reverse=True)

    def test_top_k_limits_results(self):
        vector_results = [
            (
                f"chunk_{i}",
                0.9 - i * 0.05,
                {
                    "note_path": f"{i}.md",
                    "note_title": f"{i}",
                    "heading_path": "",
                    "note_folder": "",
                    "note_date": "",
                },
                f"text {i}",
            )
            for i in range(10)
        ]

        retriever = _make_retriever(vector_results, [])
        candidates = retriever.retrieve("test", top_k=3)
        assert len(candidates) == 3


class TestHeadingPathDeserialization:
    """Tests that pipe-delimited heading paths are correctly parsed."""

    def test_pipe_delimited_heading_path(self):
        vector_results = [
            (
                "a",
                0.9,
                {
                    "note_path": "a.md",
                    "note_title": "A",
                    "heading_path": "Section|Subsection|Detail",
                    "note_folder": "",
                    "note_date": "",
                },
                "text",
            ),
        ]
        retriever = _make_retriever(vector_results, [])
        candidates = retriever.retrieve("test", top_k=10)
        assert candidates[0].heading_path == ["Section", "Subsection", "Detail"]

    def test_empty_heading_path(self):
        vector_results = [
            (
                "a",
                0.9,
                {
                    "note_path": "a.md",
                    "note_title": "A",
                    "heading_path": "",
                    "note_folder": "",
                    "note_date": "",
                },
                "text",
            ),
        ]
        retriever = _make_retriever(vector_results, [])
        candidates = retriever.retrieve("test", top_k=10)
        assert candidates[0].heading_path == []


class TestLexicalFallback:
    """Tests that lexical-only chunks are fetched from the lexical store."""

    def test_lexical_only_chunk_fetched(self):
        lexical_results = [("lex_chunk", 5.0)]
        lexical_chunks = {
            "lex_chunk": {
                "chunk_text": "Lexical only content",
                "note_path": "lex.md",
                "note_title": "Lex Note",
                "heading_path": "Section",
                "note_folder": "10_Notes",
                "note_date": "2026-01-01",
            }
        }

        retriever = _make_retriever([], lexical_results, lexical_chunks)
        candidates = retriever.retrieve("test", top_k=10)

        assert len(candidates) == 1
        assert candidates[0].chunk_text == "Lexical only content"
        assert candidates[0].note_path == "lex.md"

    def test_lexical_chunk_not_found_skipped(self):
        """If lexical store returns a chunk_id but get_chunk returns None, skip it."""
        lexical_results = [("missing_chunk", 5.0)]

        retriever = _make_retriever([], lexical_results)
        candidates = retriever.retrieve("test", top_k=10)
        assert len(candidates) == 0
