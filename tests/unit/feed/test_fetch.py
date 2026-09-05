from types import SimpleNamespace

import pytest

from secondbrain.feed import fetch as fetch_mod
from secondbrain.feed.models import FeedSource

_FEED_XML = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>c</title>
<item><title>Hello</title><link>https://x.com/a</link><description>body</description></item>
</channel></rss>"""


def _fake_parsed(entries, bozo=0):
    return SimpleNamespace(entries=entries, bozo=bozo)


@pytest.fixture
def downloads(monkeypatch):
    """Stub the network layer; returns the list of URLs requested."""
    urls = []

    def _download(url):
        urls.append(url)
        return _FEED_XML

    monkeypatch.setattr(fetch_mod, "_download", _download)
    return urls


@pytest.mark.usefixtures("downloads")
def test_fetch_source_maps_entries(monkeypatch):
    entry = SimpleNamespace(
        title="Hello",
        link="https://x.com/a",
        summary="body",
        published_parsed=(2026, 8, 4, 12, 0, 0, 0, 0, 0),
    )
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _raw: _fake_parsed([entry]))
    items = fetch_mod.fetch_source(FeedSource("https://u.example/f", "Lbl", "ai", 0.9))
    assert len(items) == 1
    assert items[0].title == "Hello"
    assert items[0].trust == 0.9
    assert items[0].published_at is not None


@pytest.mark.usefixtures("downloads")
def test_fetch_source_skips_entries_missing_title_or_link(monkeypatch):
    entries = [
        SimpleNamespace(title="", link="u", summary=""),
        SimpleNamespace(title="t", link="", summary=""),
    ]
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _raw: _fake_parsed(entries))
    assert fetch_mod.fetch_source(FeedSource("https://u.example/f", "L", "ai")) == []


def test_fetch_source_returns_empty_when_download_fails(monkeypatch):
    monkeypatch.setattr(fetch_mod, "_download", lambda _url: None)
    assert fetch_mod.fetch_source(FeedSource("https://u.example/f", "L", "ai")) == []


@pytest.mark.usefixtures("downloads")
def test_fetch_source_returns_empty_on_parse_exception(monkeypatch):
    def boom(_raw):
        raise RuntimeError("bad xml")

    monkeypatch.setattr(fetch_mod.feedparser, "parse", boom)
    assert fetch_mod.fetch_source(FeedSource("https://u.example/f", "L", "ai")) == []


@pytest.mark.usefixtures("downloads")
def test_fetch_source_drops_bozo_feed_with_no_entries(monkeypatch):
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _raw: _fake_parsed([], bozo=1))
    assert fetch_mod.fetch_source(FeedSource("https://u.example/f", "L", "ai")) == []


@pytest.mark.usefixtures("downloads")
def test_fetch_source_keeps_bozo_feed_that_still_yielded_entries(monkeypatch):
    entry = SimpleNamespace(title="t", link="https://x/1", summary="")
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _raw: _fake_parsed([entry], bozo=1))
    assert len(fetch_mod.fetch_source(FeedSource("https://u.example/f", "L", "ai"))) == 1


@pytest.mark.usefixtures("downloads")
def test_fetch_source_rejects_non_http_link_schemes(monkeypatch):
    """Feed content is attacker-influenced; only http(s) links may be stored."""
    entries = [
        SimpleNamespace(title="xss", link="javascript:alert(1)", summary=""),
        SimpleNamespace(title="data", link="data:text/html,<script>x</script>", summary=""),
        SimpleNamespace(title="file", link="file:///etc/passwd", summary=""),
        SimpleNamespace(title="ok", link="https://x.com/good", summary=""),
    ]
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _raw: _fake_parsed(entries))
    items = fetch_mod.fetch_source(FeedSource("https://u.example/f", "L", "ai"))
    assert [i.url for i in items] == ["https://x.com/good"]


@pytest.mark.usefixtures("downloads")
def test_fetch_source_scheme_check_is_case_insensitive(monkeypatch):
    entries = [SimpleNamespace(title="t", link="JavaScript:alert(1)", summary="")]
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _raw: _fake_parsed(entries))
    assert fetch_mod.fetch_source(FeedSource("https://u.example/f", "L", "ai")) == []


def test_fetch_source_refuses_non_http_source_url(monkeypatch):
    """feedparser.parse() would happily read a local file path — never reach it."""
    monkeypatch.setattr(
        fetch_mod, "_download", lambda _url: pytest.fail("must not download a file:// source")
    )
    assert fetch_mod.fetch_source(FeedSource("file:///etc/passwd", "L", "ai")) == []


def test_fetch_all_continues_past_failures(monkeypatch):
    def _download(url):
        return None if "bad" in url else _FEED_XML

    monkeypatch.setattr(fetch_mod, "_download", _download)
    monkeypatch.setattr(
        fetch_mod.feedparser,
        "parse",
        lambda _raw: _fake_parsed([SimpleNamespace(title="t", link="https://x/1", summary="")]),
    )
    sources = [
        FeedSource("https://bad.example/f", "B", "ai"),
        FeedSource("https://good.example/f", "G", "ai"),
    ]
    assert len(fetch_mod.fetch_all(sources)) == 1


class TestDownloadBounds:
    def test_download_passes_bounded_timeout(self, monkeypatch):
        seen = {}

        class _Resp:
            def raise_for_status(self):
                pass

            def iter_bytes(self):
                yield b"<rss/>"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def _stream(_method, _url, **kwargs):
            seen.update(kwargs)
            return _Resp()

        monkeypatch.setattr(fetch_mod.httpx, "stream", _stream)
        fetch_mod._download("https://x.example/f")
        assert seen["timeout"].read == fetch_mod._READ_TIMEOUT
        assert seen["timeout"].connect == fetch_mod._CONNECT_TIMEOUT

    def test_download_caps_response_size(self, monkeypatch):
        class _Resp:
            def raise_for_status(self):
                pass

            def iter_bytes(self):
                while True:  # a hostile host that never stops sending
                    yield b"x" * 65536

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(fetch_mod.httpx, "stream", lambda *_a, **_k: _Resp())
        raw = fetch_mod._download("https://x.example/f")
        assert raw is not None
        assert len(raw) <= fetch_mod._MAX_BYTES

    def test_download_returns_none_on_network_error(self, monkeypatch):
        def boom(*_a, **_k):
            raise OSError("connection reset")

        monkeypatch.setattr(fetch_mod.httpx, "stream", boom)
        assert fetch_mod._download("https://x.example/f") is None


def test_redacted_strips_basic_auth_credentials():
    """Private feeds carry user:pass in the URL — it must never reach the log."""
    out = fetch_mod._redacted("https://alice:hunter2@example.com/private/feed?k=1")
    assert "hunter2" not in out and "alice" not in out
    assert "example.com" in out


@pytest.mark.usefixtures("downloads")
def test_published_at_treats_feed_time_as_utc_not_local(monkeypatch):
    """published_parsed is UTC; mktime would shift it by the local offset."""
    entry = SimpleNamespace(
        title="t",
        link="https://x/1",
        summary="",
        published_parsed=(2026, 8, 4, 12, 0, 0, 0, 0, 0),
    )
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _raw: _fake_parsed([entry]))
    items = fetch_mod.fetch_source(FeedSource("https://u.example/f", "L", "ai"))
    assert items[0].published_at == "2026-08-04T12:00:00+00:00"


@pytest.mark.usefixtures("downloads")
def test_published_at_falls_back_to_updated_parsed(monkeypatch):
    entry = SimpleNamespace(
        title="t", link="https://x/1", summary="", updated_parsed=(2026, 1, 2, 3, 4, 5, 0, 0, 0)
    )
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _raw: _fake_parsed([entry]))
    items = fetch_mod.fetch_source(FeedSource("https://u.example/f", "L", "ai"))
    assert items[0].published_at == "2026-01-02T03:04:05+00:00"


@pytest.mark.usefixtures("downloads")
def test_published_at_is_none_without_a_date(monkeypatch):
    entry = SimpleNamespace(title="t", link="https://x/1", summary="")
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _raw: _fake_parsed([entry]))
    items = fetch_mod.fetch_source(FeedSource("https://u.example/f", "L", "ai"))
    assert items[0].published_at is None
