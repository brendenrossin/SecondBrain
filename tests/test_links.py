"""Tests for the wiki link parser."""

from secondbrain.vault.links import extract_wiki_links


class TestExtractWikiLinks:
    def test_simple_link(self) -> None:
        assert extract_wiki_links("See [[Simple Note]] for details") == ["Simple Note"]

    def test_link_with_alias(self) -> None:
        assert extract_wiki_links("See [[Note Title|alias]] here") == ["Note Title"]

    def test_link_with_heading(self) -> None:
        assert extract_wiki_links("See [[Note Title#heading]]") == ["Note Title"]

    def test_link_with_heading_and_alias(self) -> None:
        assert extract_wiki_links("See [[Note Title#heading|alias]]") == ["Note Title"]

    def test_multiple_links(self) -> None:
        text = "See [[Note A]] and [[Note B]] and [[Note C]]"
        assert extract_wiki_links(text) == ["Note A", "Note B", "Note C"]

    def test_deduplication(self) -> None:
        text = "See [[Note A]] and later [[Note A]] again"
        assert extract_wiki_links(text) == ["Note A"]

    def test_no_links(self) -> None:
        assert extract_wiki_links("No links here at all") == []

    def test_empty_string(self) -> None:
        assert extract_wiki_links("") == []

    def test_link_inside_inline_code_excluded(self) -> None:
        assert extract_wiki_links("Use `[[Not A Link]]` in code") == []

    def test_link_inside_fenced_code_excluded(self) -> None:
        text = "Before\n```\n[[Not A Link]]\n```\nAfter [[Real Link]]"
        assert extract_wiki_links(text) == ["Real Link"]

    def test_link_outside_code_kept(self) -> None:
        text = "`code` then [[Real Link]]"
        assert extract_wiki_links(text) == ["Real Link"]

    def test_mixed_formats(self) -> None:
        text = "[[A]] and [[B|alias]] and [[C#heading]] and [[D#heading|alias]]"
        assert extract_wiki_links(text) == ["A", "B", "C", "D"]

    def test_link_with_spaces_in_title(self) -> None:
        assert extract_wiki_links("[[My Long Note Title]]") == ["My Long Note Title"]
