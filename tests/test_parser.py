"""Functional tests for vault/parser.py — title extraction and markdown parsing."""

from secondbrain.vault.parser import parse_markdown


class TestExtractTitle:
    """Tests for the title extraction precedence: frontmatter > H1 > filename."""

    def test_title_from_frontmatter(self):
        content = "---\ntitle: My Custom Title\n---\n\n# Heading One\n\nSome content."
        note = parse_markdown("notes/test.md", content)
        assert note.title == "My Custom Title"

    def test_title_from_h1_when_no_frontmatter_title(self):
        content = "---\ntags: [foo]\n---\n\n# First Heading\n\nBody text."
        note = parse_markdown("notes/test.md", content)
        assert note.title == "First Heading"

    def test_title_from_filename_when_no_frontmatter_or_h1(self):
        content = "Just some plain text with no headings and no frontmatter."
        note = parse_markdown("notes/my-note.md", content)
        assert note.title == "my-note"

    def test_title_from_filename_when_only_h2_exists(self):
        content = "## This is H2 not H1\n\nSome text."
        note = parse_markdown("notes/fallback.md", content)
        assert note.title == "fallback"

    def test_non_string_frontmatter_title_skipped(self):
        """If frontmatter title is a list, it should fall back to H1."""
        content = "---\ntitle:\n  - item1\n  - item2\n---\n\n# Real Title\n\nContent."
        note = parse_markdown("notes/test.md", content)
        assert note.title == "Real Title"

    def test_dict_frontmatter_title_skipped(self):
        """If frontmatter title is a dict, it should fall back to H1."""
        content = "---\ntitle:\n  key: value\n---\n\n# Actual Title\n\nContent."
        note = parse_markdown("notes/test.md", content)
        assert note.title == "Actual Title"

    def test_multiple_h1_uses_first(self):
        content = "# First H1\n\nSome text.\n\n# Second H1\n\nMore text."
        note = parse_markdown("notes/test.md", content)
        assert note.title == "First H1"

    def test_empty_frontmatter(self):
        content = "---\n---\n\n# Title After Empty Frontmatter\n\nContent."
        note = parse_markdown("notes/test.md", content)
        assert note.title == "Title After Empty Frontmatter"

    def test_no_frontmatter_no_headings_uses_filename_stem(self):
        content = "Plain text only, no markdown structure at all."
        note = parse_markdown("path/to/2026-02-14.md", content)
        assert note.title == "2026-02-14"

    def test_frontmatter_title_with_special_chars(self):
        content = '---\ntitle: "Title: With Colon & Ampersand"\n---\n\nContent.'
        note = parse_markdown("notes/test.md", content)
        assert note.title == "Title: With Colon & Ampersand"

    def test_h1_with_leading_trailing_whitespace(self):
        content = "#   Spaced Title   \n\nContent."
        note = parse_markdown("notes/test.md", content)
        assert note.title == "Spaced Title"


class TestParseMarkdown:
    """Tests for the full parse_markdown function."""

    def test_frontmatter_extracted_as_dict(self):
        content = "---\ntags: [a, b]\nstatus: active\n---\n\n# Title\n\nBody."
        note = parse_markdown("test.md", content)
        assert note.frontmatter == {"tags": ["a", "b"], "status": "active"}

    def test_content_excludes_frontmatter(self):
        content = "---\ntitle: Test\n---\n\n# Test\n\nBody text here."
        note = parse_markdown("test.md", content)
        assert "---" not in note.content
        assert "Body text here." in note.content

    def test_note_path_preserved(self):
        note = parse_markdown("folder/subfolder/note.md", "# Title\n\nContent.")
        assert note.path == "folder/subfolder/note.md"

    def test_empty_content(self):
        note = parse_markdown("empty.md", "")
        assert note.title == "empty"
        assert note.content == ""
        assert note.frontmatter == {}

    def test_content_with_only_frontmatter(self):
        content = "---\ntitle: Only Frontmatter\n---\n"
        note = parse_markdown("test.md", content)
        assert note.title == "Only Frontmatter"
        assert note.content.strip() == ""
