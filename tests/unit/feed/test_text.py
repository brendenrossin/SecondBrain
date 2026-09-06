"""Unit tests for `feed.text.strip_html`.

Its own file because `text` is its own module: both `fetch` (cleaning on the way
in) and `stores.feed` (backfilling older rows) depend on this contract.
"""

from secondbrain.feed.text import strip_html


class TestStripHtml:
    def test_removes_tags_and_keeps_text(self):
        raw = '<p><strong>TIL:</strong> <a href="https://til.example/x">Blender</a> with agents</p>'
        assert strip_html(raw) == "TIL: Blender with agents"

    def test_drops_urls_that_lived_in_hrefs(self):
        # The href is exactly what the summarizer used to copy into its takes.
        assert "example" not in strip_html('<a href="https://example.com">text</a>')

    def test_separates_adjacent_block_elements(self):
        assert strip_html("<p>one</p><p>two</p>") == "one two"

    def test_unescapes_entities(self):
        assert strip_html("Ben &amp; Jerry&#8217;s") == "Ben & Jerry’s"

    def test_discards_script_and_style_bodies(self):
        assert strip_html("<script>var x=1;</script>Visible") == "Visible"
        assert strip_html("<style>p{color:red}</style>Visible") == "Visible"

    def test_collapses_whitespace(self):
        assert strip_html("a\n\n   b\tc") == "a b c"

    def test_plain_text_passes_through(self):
        assert strip_html("Plain text, no markup") == "Plain text, no markup"

    def test_unclosed_tags_do_not_raise(self):
        assert strip_html("<p>unclosed <b>bold") == "unclosed bold"

    def test_empty_input(self):
        assert strip_html("") == ""


class TestStripHtmlHostileInput:
    def test_entity_encoded_markup_never_decodes_into_live_markup(self):
        # convert_charrefs decodes AFTER tags are removed, so "&lt;script&gt;"
        # would otherwise leave the sanitizer as a working <script> tag.
        assert strip_html("&lt;script&gt;alert(1)&lt;/script&gt;") == "alert(1)"
        assert "<" not in strip_html("&#60;img src=x onerror=alert(1)&#62;")

    def test_is_idempotent(self):
        # The store's backfill re-reads its own output; a second pass must be a
        # no-op or it strips prose that the first pass legitimately produced.
        for raw in [
            "&lt;b&gt;hi&lt;/b&gt;",
            "Rust stabilizes &lt;T&gt; coercions",
            "<p>Tom &amp; Jerry</p>",
            "AT&amp;T earnings",
        ]:
            once = strip_html(raw)
            assert strip_html(once) == once, raw

    def test_prose_between_literal_angle_brackets_survives(self):
        assert strip_html("Why x<y matters > 3") == "Why x<y matters > 3"
        assert strip_html("Score 3<4 today") == "Score 3<4 today"

    def test_unclosed_script_does_not_blank_the_field(self):
        # HTMLParser swallows to EOF in CDATA mode; the fallback keeps the text.
        assert strip_html("<script>alert(1)") == "alert(1)"

    def test_comments_are_removed(self):
        assert strip_html("Hello <!-- hidden --> world") == "Hello world"

    def test_ampersand_prose_is_untouched(self):
        assert strip_html("Tom &amp; Jerry") == "Tom & Jerry"
