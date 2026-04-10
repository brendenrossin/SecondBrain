"""Tests for wiki API scoring logic and models."""

from secondbrain.api.wiki import compute_wiki_suggestion


class TestWikiSuggestionScoring:
    def test_eligible_answer(self) -> None:
        suggestion = compute_wiki_suggestion(
            "PASS", "A" * 300, ["Note A", "Note B", "Note C"], "How does X relate to Y?"
        )
        assert suggestion.eligible

    def test_ineligible_short_answer(self) -> None:
        suggestion = compute_wiki_suggestion(
            "PASS", "Yes.", ["Note A", "Note B", "Note C"], "Is X true?"
        )
        assert not suggestion.eligible

    def test_ineligible_no_results(self) -> None:
        suggestion = compute_wiki_suggestion("NO_RESULTS", "A" * 300, [], "What is X?")
        assert not suggestion.eligible

    def test_ineligible_factual_lookup(self) -> None:
        suggestion = compute_wiki_suggestion(
            "PASS", "A" * 300, ["Note A", "Note B", "Note C"], "When was the meeting?"
        )
        assert not suggestion.eligible

    def test_eligible_factual_lookup_with_long_answer(self) -> None:
        """A 'when' query with a long answer should still be eligible."""
        suggestion = compute_wiki_suggestion(
            "PASS", "A" * 600, ["Note A", "Note B", "Note C"], "When did this happen?"
        )
        assert suggestion.eligible

    def test_ineligible_where_query_short_answer(self) -> None:
        suggestion = compute_wiki_suggestion(
            "PASS", "A" * 300, ["Note A", "Note B", "Note C"], "Where is the office?"
        )
        assert not suggestion.eligible

    def test_ineligible_who_query_short_answer(self) -> None:
        suggestion = compute_wiki_suggestion(
            "PASS", "A" * 300, ["Note A", "Note B", "Note C"], "Who leads the team?"
        )
        assert not suggestion.eligible

    def test_ineligible_irrelevant_retrieval_label(self) -> None:
        suggestion = compute_wiki_suggestion(
            "IRRELEVANT", "A" * 300, ["Note A", "Note B", "Note C"], "How does X work?"
        )
        assert not suggestion.eligible

    def test_ineligible_hallucination_risk_label(self) -> None:
        suggestion = compute_wiki_suggestion(
            "HALLUCINATION_RISK", "A" * 300, ["Note A", "Note B", "Note C"], "How does X work?"
        )
        assert not suggestion.eligible

    def test_ineligible_too_few_citations(self) -> None:
        suggestion = compute_wiki_suggestion(
            "PASS", "A" * 300, ["Note A", "Note B"], "How does X work?"
        )
        assert not suggestion.eligible

    def test_deduplicates_citation_titles(self) -> None:
        """Duplicate citation titles count as one source."""
        suggestion = compute_wiki_suggestion(
            "PASS", "A" * 300, ["Note A", "Note A", "Note A"], "How does X work?"
        )
        assert not suggestion.eligible

    def test_eligible_reason_mentions_source_count(self) -> None:
        suggestion = compute_wiki_suggestion(
            "PASS",
            "A" * 300,
            ["Note A", "Note B", "Note C", "Note D"],
            "How does X relate to Y?",
        )
        assert suggestion.eligible
        assert "4" in suggestion.reason

    def test_ineligible_reason_is_set(self) -> None:
        suggestion = compute_wiki_suggestion("NO_RESULTS", "A" * 300, [], "What is X?")
        assert not suggestion.eligible
        assert suggestion.reason != ""

    def test_exactly_three_citations_eligible(self) -> None:
        """Exactly 3 unique citations should meet the minimum threshold."""
        suggestion = compute_wiki_suggestion(
            "PASS",
            "A" * 300,
            ["Note A", "Note B", "Note C"],
            "How does this framework work?",
        )
        assert suggestion.eligible

    def test_query_case_insensitive_factual_check(self) -> None:
        """Factual prefix check should be case-insensitive."""
        suggestion = compute_wiki_suggestion(
            "PASS", "A" * 300, ["Note A", "Note B", "Note C"], "WHEN was the meeting?"
        )
        assert not suggestion.eligible
