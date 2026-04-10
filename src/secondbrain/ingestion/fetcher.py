"""Content fetcher: extract plain text from web articles, YouTube, and PDFs."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

import httpx

MAX_HTML_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB
FETCH_TIMEOUT = 30.0
YOUTUBE_TIMEOUT = 60.0

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_YOUTUBE_SHORT_HOST = "youtu.be"
_YOUTUBE_PATH_PREFIXES = ("/shorts/", "/embed/")


class ContentType(StrEnum):
    WEB_ARTICLE = "web_article"
    YOUTUBE = "youtube"
    PDF = "pdf"


@dataclass
class FetchedContent:
    source_url: str
    title: str
    content_type: ContentType
    raw_text: str
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.raw_text)


def detect_content_type(url: str) -> ContentType:
    """Detect the content type of a URL.

    Raises:
        ValueError: If the URL is invalid or uses a non-HTTP scheme.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Invalid URL: {url!r}") from exc

    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url!r}")

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only HTTP/HTTPS URLs are supported, got scheme: {parsed.scheme!r}")

    host = parsed.netloc.lower()
    path = parsed.path.lower()

    # YouTube detection
    if host in _YOUTUBE_HOSTS:
        if "/watch" in path:
            return ContentType.YOUTUBE
        for prefix in _YOUTUBE_PATH_PREFIXES:
            if path.startswith(prefix):
                return ContentType.YOUTUBE
    if host == _YOUTUBE_SHORT_HOST:
        return ContentType.YOUTUBE

    # PDF detection — path must end with .pdf
    if path.endswith(".pdf"):
        return ContentType.PDF

    return ContentType.WEB_ARTICLE


def fetch_web_article(url: str) -> FetchedContent:
    """Fetch and extract a web article as Markdown text.

    Raises:
        ValueError: If the response exceeds MAX_HTML_BYTES.
        httpx.HTTPError: On network errors.
    """
    from bs4 import BeautifulSoup
    from markdownify import markdownify
    from readability import Document

    response = httpx.get(
        url,
        follow_redirects=True,
        timeout=FETCH_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()

    if len(response.content) > MAX_HTML_BYTES:
        raise ValueError(
            f"Response too large: {len(response.content)} bytes (max {MAX_HTML_BYTES})"
        )

    html = response.text
    doc = Document(html)
    title = doc.title()
    readable_html = doc.summary()

    # Strip unwanted tags before converting to markdown
    soup = BeautifulSoup(readable_html, "html.parser")
    for tag in soup.find_all(["img", "script", "style"]):
        tag.decompose()

    markdown = markdownify(str(soup), heading_style="ATX", strip=["a"])

    # Clean up excessive blank lines
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()

    return FetchedContent(
        source_url=url,
        title=title or "",
        content_type=ContentType.WEB_ARTICLE,
        raw_text=markdown,
        metadata={"final_url": str(response.url)},
    )


def _parse_vtt(vtt_text: str) -> str:
    """Parse a VTT subtitle file into plain text.

    Strips timestamps, HTML tags, deduplicates consecutive identical lines,
    and joins with spaces.
    """
    lines: list[str] = []
    prev_line = ""

    for raw_line in vtt_text.splitlines():
        line = raw_line.strip()

        # Skip VTT header, blank lines, and timestamp lines
        if not line:
            continue
        if line.startswith("WEBVTT"):
            continue
        if re.match(r"^\d{2}:\d{2}[:\.]", line):
            continue
        if "-->" in line:
            continue
        # Skip cue identifiers (pure digit lines or NOTE blocks)
        if line.isdigit():
            continue
        if line.startswith("NOTE"):
            continue

        # Strip HTML tags
        line = re.sub(r"<[^>]+>", "", line).strip()

        if not line:
            continue

        # Deduplicate consecutive identical lines
        if line != prev_line:
            lines.append(line)
            prev_line = line

    return " ".join(lines)


def fetch_youtube_transcript(url: str) -> FetchedContent:
    """Fetch a YouTube video's transcript (or description as fallback).

    Raises:
        ValueError: On download errors or unsupported videos.
    """
    import yt_dlp  # type: ignore[import-untyped]

    ydl_opts: dict[str, object] = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
        "socket_timeout": YOUTUBE_TIMEOUT,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise ValueError(f"Could not extract info from YouTube URL: {url!r}")

    title: str = info.get("title") or ""
    channel: str = info.get("channel") or info.get("uploader") or ""
    duration: int | None = info.get("duration")
    description: str = info.get("description") or ""

    # Try manual subtitles first, then auto-captions
    subtitle_url: str | None = None
    for sub_key in ("subtitles", "automatic_captions"):
        sub_data = info.get(sub_key, {})
        en_subs = sub_data.get("en", [])
        for fmt in en_subs:
            if fmt.get("ext") in ("vtt", "srv3"):
                subtitle_url = fmt.get("url")
                break
        if subtitle_url:
            break

    raw_text = ""

    if subtitle_url:
        try:
            vtt_response = httpx.get(
                subtitle_url,
                timeout=FETCH_TIMEOUT,
                headers={"User-Agent": _USER_AGENT},
            )
            vtt_response.raise_for_status()
            raw_text = _parse_vtt(vtt_response.text)
        except httpx.HTTPError:
            pass  # Fall through to description

    if not raw_text and description:
        raw_text = description

    metadata: dict[str, object] = {"channel": channel}
    if duration is not None:
        metadata["duration_seconds"] = duration

    return FetchedContent(
        source_url=url,
        title=title,
        content_type=ContentType.YOUTUBE,
        raw_text=raw_text,
        metadata=metadata,
    )


def fetch_pdf(url: str) -> FetchedContent:
    """Download and extract text from a PDF URL.

    Raises:
        ValueError: If the PDF exceeds MAX_PDF_BYTES.
        httpx.HTTPError: On network errors.
    """
    import pymupdf4llm  # type: ignore[import-untyped]

    response = httpx.get(
        url,
        follow_redirects=True,
        timeout=FETCH_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()

    if len(response.content) > MAX_PDF_BYTES:
        raise ValueError(f"PDF too large: {len(response.content)} bytes (max {MAX_PDF_BYTES})")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    try:
        markdown = pymupdf4llm.to_markdown(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Try to extract title from first heading
    title = ""
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            break

    if not title:
        # Fall back to filename from URL
        parsed = urlparse(url)
        title = Path(parsed.path).stem.replace("-", " ").replace("_", " ").title()

    return FetchedContent(
        source_url=url,
        title=title,
        content_type=ContentType.PDF,
        raw_text=markdown,
        metadata={"source_filename": Path(urlparse(url).path).name},
    )


def fetch_content(url: str) -> FetchedContent:
    """Main dispatcher: detect content type and fetch accordingly.

    Raises:
        ValueError: For invalid URLs or unsupported schemes.
        httpx.HTTPError: On network errors.
    """
    content_type = detect_content_type(url)
    if content_type == ContentType.YOUTUBE:
        return fetch_youtube_transcript(url)
    elif content_type == ContentType.PDF:
        return fetch_pdf(url)
    else:
        return fetch_web_article(url)
