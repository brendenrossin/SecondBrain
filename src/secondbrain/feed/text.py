"""Plain-text cleanup for feed content.

Its own module because two layers need it: `fetch` cleans text on the way in,
and `stores.feed` backfills rows written before that cleaning existed.
"""

import html
import re
from html.parser import HTMLParser

_WHITESPACE = re.compile(r"\s+")
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SKIPPED_ELEMENTS = frozenset({"script", "style"})

# Deliberately an allowlist of real HTML element names rather than `<[^>]*>`.
# Feed titles contain prose like "Why x<y matters > 3", and the permissive
# pattern reads "<y matters >" as a tag and deletes four words of the headline.
_HTML_ELEMENT = re.compile(
    r"</?(?:a|abbr|audio|b|blockquote|br|cite|code|dd|div|dl|dt|em|figcaption|figure"
    r"|h[1-6]|hr|i|iframe|img|li|mark|ol|p|pre|script|small|source|span|strong|style"
    r"|sub|sup|table|tbody|td|th|thead|time|tr|u|ul|video)\b[^<>]*>",
    re.IGNORECASE,
)


class _TextExtractor(HTMLParser):
    """Collect visible text, discarding tags and the contents of script/style."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],  # noqa: ARG002 - HTMLParser override signature
    ) -> None:
        # A space per tag boundary keeps "<p>a</p><p>b</p>" from becoming "ab";
        # the whitespace collapse below tidies up the extras.
        self.parts.append(" ")
        if tag in _SKIPPED_ELEMENTS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(" ")
        if tag in _SKIPPED_ELEMENTS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def _strip_tags(raw: str) -> str:
    """Regex-only fallback for markup HTMLParser cannot be trusted with."""
    return html.unescape(_HTML_ELEMENT.sub(" ", raw))


def _parse_text(raw: str) -> str:
    """Visible text via HTMLParser, or a regex fallback if it chokes."""
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
        return "".join(parser.parts)
    except Exception:
        # HTMLParser is lenient, but a pathological entry must not kill the item.
        return _strip_tags(raw)


def strip_html(raw: str) -> str:
    """Plain text from an RSS summary, which is HTML far more often than not.

    Storing the markup verbatim broke three things at once: the UI printed
    literal "<p><strong>" at the reader, the summarizer prompt paid tokens for
    tags and copied hrefs out of them, and the snippet cap spent its budget on
    markup instead of prose. Strip before truncating, never after.

    Output never contains live markup and running it twice changes nothing —
    both matter because the store's backfill re-reads its own output, and
    because a later consumer (a digest push, a note write) may not escape the
    way React does.
    """
    if not raw:
        return ""
    if _HTML_ELEMENT.search(raw):
        text = _parse_text(raw)
        # An unclosed <script> or <style> makes HTMLParser swallow everything
        # after it. Falling back keeps the prose instead of blanking the field.
        if not text.strip():
            text = _strip_tags(raw)
    else:
        text = html.unescape(raw)
    # Entity decoding happens above, so encoded markup ("&lt;script&gt;") only
    # becomes recognisable now — strip it here or hand a live tag to the caller.
    return _WHITESPACE.sub(" ", _COMMENT.sub(" ", _HTML_ELEMENT.sub(" ", text))).strip()
