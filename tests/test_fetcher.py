"""Tests for the content fetcher module."""

from __future__ import annotations

import pytest

from secondbrain.ingestion.fetcher import (
    ContentType,
    FetchedContent,
    detect_content_type,
)


class TestDetectContentType:
    def test_youtube_url(self) -> None:
        assert detect_content_type("https://www.youtube.com/watch?v=abc123") == ContentType.YOUTUBE

    def test_youtube_short_url(self) -> None:
        assert detect_content_type("https://youtu.be/abc123") == ContentType.YOUTUBE

    def test_youtube_shorts_url(self) -> None:
        assert detect_content_type("https://www.youtube.com/shorts/abc123") == ContentType.YOUTUBE

    def test_youtube_embed_url(self) -> None:
        assert detect_content_type("https://www.youtube.com/embed/abc123") == ContentType.YOUTUBE

    def test_pdf_url(self) -> None:
        assert detect_content_type("https://arxiv.org/pdf/2301.00001.pdf") == ContentType.PDF

    def test_web_article_url(self) -> None:
        assert detect_content_type("https://example.com/blog/post") == ContentType.WEB_ARTICLE

    def test_web_article_no_extension(self) -> None:
        assert (
            detect_content_type("https://news.ycombinator.com/item?id=12345")
            == ContentType.WEB_ARTICLE
        )

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid URL"):
            detect_content_type("not-a-url")

    def test_non_http_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Only HTTP"):
            detect_content_type("ftp://example.com/file")

    def test_http_scheme_accepted(self) -> None:
        assert detect_content_type("http://example.com/article") == ContentType.WEB_ARTICLE

    def test_pdf_query_param_not_matched(self) -> None:
        # PDF detection is based on path, not query params
        assert (
            detect_content_type("https://example.com/download?file=report.pdf")
            == ContentType.WEB_ARTICLE
        )


class TestFetchedContent:
    def test_creation(self) -> None:
        content = FetchedContent(
            source_url="https://example.com",
            title="Test Article",
            content_type=ContentType.WEB_ARTICLE,
            raw_text="Hello world",
            metadata={"author": "Test"},
        )
        assert content.source_url == "https://example.com"
        assert content.title == "Test Article"
        assert content.content_type == ContentType.WEB_ARTICLE
        assert content.raw_text == "Hello world"
        assert content.metadata == {"author": "Test"}

    def test_char_count(self) -> None:
        text = "Hello world"
        content = FetchedContent(
            source_url="https://example.com",
            title="Test",
            content_type=ContentType.WEB_ARTICLE,
            raw_text=text,
            metadata={},
        )
        assert content.char_count == len(text)

    def test_char_count_empty(self) -> None:
        content = FetchedContent(
            source_url="https://example.com",
            title="Test",
            content_type=ContentType.WEB_ARTICLE,
            raw_text="",
            metadata={},
        )
        assert content.char_count == 0

    def test_default_metadata(self) -> None:
        content = FetchedContent(
            source_url="https://example.com",
            title="Test",
            content_type=ContentType.PDF,
            raw_text="content",
            metadata={},
        )
        assert content.metadata == {}
