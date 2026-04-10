"""Tests for the WikiCompiler module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from secondbrain.ingestion.compiler import WikiCompiler, slugify_title
from secondbrain.ingestion.fetcher import ContentType, FetchedContent

# ---------------------------------------------------------------------------
# slugify_title
# ---------------------------------------------------------------------------


class TestSlugifyTitle:
    def test_basic(self) -> None:
        assert slugify_title("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        assert slugify_title("What's New in Python 3.12?") == "whats-new-in-python-312"

    def test_excessive_hyphens(self) -> None:
        assert slugify_title("Hello --- World") == "hello-world"

    def test_long_title_truncated(self) -> None:
        slug = slugify_title("word " * 50)
        assert len(slug) <= 80

    def test_lowercase(self) -> None:
        assert slugify_title("ALL CAPS TITLE") == "all-caps-title"

    def test_leading_trailing_hyphens_stripped(self) -> None:
        slug = slugify_title("  -- title --  ")
        assert not slug.startswith("-")
        assert not slug.endswith("-")

    def test_empty_string(self) -> None:
        assert slugify_title("") == ""

    def test_only_special_chars(self) -> None:
        # Should yield empty or just hyphens stripped
        result = slugify_title("!@#$%^&*()")
        assert result == ""


# ---------------------------------------------------------------------------
# WikiCompiler.compile
# ---------------------------------------------------------------------------


def _make_mock_text_response(body: str) -> MagicMock:
    """Build a mock Anthropic message response with a text block."""
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = body

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage = MagicMock(input_tokens=200, output_tokens=100)

    return mock_response


class TestWikiCompilerCompile:
    def setup_method(self) -> None:
        self.compiler = WikiCompiler(api_key="fake-key")
        self.content = FetchedContent(
            source_url="https://example.com/article",
            title="My Test Article",
            content_type=ContentType.WEB_ARTICLE,
            raw_text="Some article text.",
        )

    def test_compile_returns_markdown_with_frontmatter(self) -> None:
        mock_response = _make_mock_text_response("## Key Concepts\n\nContent about the topic.")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            markdown, title = self.compiler.compile(self.content)

        assert "---" in markdown
        assert "title:" in markdown
        assert "source:" in markdown
        assert "source_type:" in markdown
        assert "compiled_date:" in markdown
        assert "tags:" in markdown
        assert "## Key Concepts" in markdown

    def test_compile_returns_title(self) -> None:
        mock_response = _make_mock_text_response("## Content\n\nSome text.")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            _, title = self.compiler.compile(self.content)

        assert isinstance(title, str)
        assert len(title) > 0

    def test_compile_frontmatter_has_correct_source_url(self) -> None:
        mock_response = _make_mock_text_response("## Content")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            markdown, _ = self.compiler.compile(self.content)

        assert "https://example.com/article" in markdown

    def test_compile_frontmatter_has_correct_source_type(self) -> None:
        mock_response = _make_mock_text_response("## Content")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            markdown, _ = self.compiler.compile(self.content)

        assert "web_article" in markdown

    def test_compile_includes_source_attribution_line(self) -> None:
        mock_response = _make_mock_text_response("## Content")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            markdown, _ = self.compiler.compile(self.content)

        # Body should contain source attribution
        assert "https://example.com/article" in markdown

    def test_compile_with_vault_manifest(self) -> None:
        """vault_manifest should be passed into the system prompt."""
        mock_response = _make_mock_text_response("## Content")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            markdown, _ = self.compiler.compile(
                self.content, vault_manifest="Existing topics: Python, AI"
            )
            call_kwargs = mock_client.messages.create.call_args
            system_prompt = call_kwargs[1]["system"]
            assert "Existing topics: Python, AI" in system_prompt

    def test_compile_logs_usage_when_store_provided(self) -> None:
        mock_response = _make_mock_text_response("## Content")
        mock_store = MagicMock()
        compiler = WikiCompiler(api_key="fake-key", usage_store=mock_store)
        with patch.object(compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            compiler.compile(self.content)

        mock_store.log_usage.assert_called_once()
        call_kwargs = mock_store.log_usage.call_args[1]
        assert call_kwargs["usage_type"] == "wiki_compile"


# ---------------------------------------------------------------------------
# WikiCompiler.compile_answer
# ---------------------------------------------------------------------------


class TestWikiCompilerCompileAnswer:
    def setup_method(self) -> None:
        self.compiler = WikiCompiler(api_key="fake-key")

    def test_compile_answer_includes_citations(self) -> None:
        mock_response = _make_mock_text_response("## Summary\n\nRestructured answer with headings.")
        citations = ["Note Alpha", "Note Beta"]
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            markdown, title = self.compiler.compile_answer(
                answer_text="Some chat answer.",
                query="How does X relate to Y?",
                citations=citations,
            )

        assert "citations:" in markdown
        assert "Note Alpha" in markdown
        assert "Note Beta" in markdown

    def test_compile_answer_title_format(self) -> None:
        mock_response = _make_mock_text_response("## Answer")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            _, title = self.compiler.compile_answer(
                answer_text="Answer text.",
                query="What is machine learning?",
                citations=[],
            )

        assert title.startswith("Synthesized:")
        assert "What is machine learning?" in title

    def test_compile_answer_long_query_truncated_in_title(self) -> None:
        long_query = "q" * 200
        mock_response = _make_mock_text_response("## Answer")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            _, title = self.compiler.compile_answer(
                answer_text="Answer.",
                query=long_query,
                citations=[],
            )

        # Title format: "Synthesized: {query[:100]}"
        assert len(title) <= len("Synthesized: ") + 100

    def test_compile_answer_frontmatter_has_synthesis_source_type(self) -> None:
        mock_response = _make_mock_text_response("## Answer")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            markdown, _ = self.compiler.compile_answer(
                answer_text="Answer text.",
                query="Test query",
                citations=[],
            )

        assert 'source_type: "synthesis"' in markdown or "source_type: synthesis" in markdown

    def test_compile_answer_frontmatter_has_query_field(self) -> None:
        mock_response = _make_mock_text_response("## Answer")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            markdown, _ = self.compiler.compile_answer(
                answer_text="Answer text.",
                query="Test query",
                citations=[],
            )

        assert "query:" in markdown

    def test_compile_answer_empty_citations(self) -> None:
        mock_response = _make_mock_text_response("## Answer")
        with patch.object(self.compiler, "_client") as mock_client:
            mock_client.messages.create.return_value = mock_response
            markdown, _ = self.compiler.compile_answer(
                answer_text="Answer.",
                query="Query",
                citations=[],
            )

        # Should still have citations field
        assert "citations:" in markdown


# ---------------------------------------------------------------------------
# WikiCompiler.find_existing_by_source
# ---------------------------------------------------------------------------


class TestWikiCompilerDuplicateCheck:
    def setup_method(self) -> None:
        self.compiler = WikiCompiler(api_key="fake-key")

    def test_find_existing_wiki_page_by_source(self, tmp_path: Path) -> None:
        url = "https://example.com/some-article"
        wiki_file = tmp_path / "some-article.md"
        wiki_file.write_text(
            f'---\ntitle: "Some Article"\nsource: "{url}"\n---\n\n## Content\n',
            encoding="utf-8",
        )

        result = self.compiler.find_existing_by_source(tmp_path, url)
        assert result == wiki_file

    def test_no_existing_returns_none(self, tmp_path: Path) -> None:
        result = self.compiler.find_existing_by_source(tmp_path, "https://example.com/new")
        assert result is None

    def test_different_source_not_matched(self, tmp_path: Path) -> None:
        url_stored = "https://example.com/stored"
        url_query = "https://example.com/other"
        wiki_file = tmp_path / "stored.md"
        wiki_file.write_text(
            f'---\ntitle: "Stored"\nsource: "{url_stored}"\n---\n\n## Content\n',
            encoding="utf-8",
        )

        result = self.compiler.find_existing_by_source(tmp_path, url_query)
        assert result is None

    def test_finds_among_multiple_files(self, tmp_path: Path) -> None:
        url_target = "https://example.com/target"

        (tmp_path / "other.md").write_text(
            '---\nsource: "https://example.com/other"\n---\n',
            encoding="utf-8",
        )
        target_file = tmp_path / "target.md"
        target_file.write_text(
            f'---\nsource: "{url_target}"\n---\n',
            encoding="utf-8",
        )

        result = self.compiler.find_existing_by_source(tmp_path, url_target)
        assert result == target_file
