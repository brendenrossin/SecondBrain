from types import SimpleNamespace

from secondbrain.feed import fetch as fetch_mod
from secondbrain.feed.models import FeedSource


def _fake_parsed(entries, bozo=0):
    return SimpleNamespace(entries=entries, bozo=bozo)


def test_fetch_source_maps_entries(monkeypatch):
    entry = SimpleNamespace(
        title="Hello",
        link="https://x.com/a",
        summary="body",
        published_parsed=(2026, 8, 4, 12, 0, 0, 0, 0, 0),
    )
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _url: _fake_parsed([entry]))
    items = fetch_mod.fetch_source(FeedSource("u", "Lbl", "ai", 0.9))
    assert len(items) == 1
    assert items[0].title == "Hello"
    assert items[0].trust == 0.9
    assert items[0].published_at is not None


def test_fetch_source_skips_entries_missing_title_or_link(monkeypatch):
    entries = [
        SimpleNamespace(title="", link="u", summary=""),
        SimpleNamespace(title="t", link="", summary=""),
    ]
    monkeypatch.setattr(fetch_mod.feedparser, "parse", lambda _url: _fake_parsed(entries))
    assert fetch_mod.fetch_source(FeedSource("u", "L", "ai")) == []


def test_fetch_source_returns_empty_on_exception(monkeypatch):
    def boom(_url):
        raise RuntimeError("network down")

    monkeypatch.setattr(fetch_mod.feedparser, "parse", boom)
    assert fetch_mod.fetch_source(FeedSource("u", "L", "ai")) == []


def test_fetch_all_continues_past_failures(monkeypatch):
    def parse(url):
        if url == "bad":
            raise RuntimeError("down")
        return _fake_parsed([SimpleNamespace(title="t", link="https://x/1", summary="")])

    monkeypatch.setattr(fetch_mod.feedparser, "parse", parse)
    sources = [FeedSource("bad", "B", "ai"), FeedSource("good", "G", "ai")]
    assert len(fetch_mod.fetch_all(sources)) == 1
