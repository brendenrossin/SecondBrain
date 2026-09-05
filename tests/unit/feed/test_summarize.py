from types import SimpleNamespace

from secondbrain.feed import summarize as summarize_mod
from secondbrain.feed.models import FeedItem


def _item(url="u", title="t", type="ai", snippet="snip"):
    return FeedItem(url=url, source_label="s", type=type, title=title, snippet=snippet)


def _settings(key=None, model="claude-haiku-4-5"):
    return SimpleNamespace(anthropic_api_key=key, feed_summary_model=model)


def test_prompt_includes_type_and_url():
    p = summarize_mod.build_summary_prompt([_item(url="https://x/1", title="Agents", type="ai")])
    assert "[ai]" in p and "https://x/1" in p and "Agents" in p


def test_parse_valid_json():
    text = (
        'prose {"sections":[{"heading":"AI","items":[{"url":"u","title":"t","take":"hot"}]}]} more'
    )
    s = summarize_mod.parse_summary_response(text, [_item()])
    assert s.generated is True
    assert s.sections[0].heading == "AI"
    assert s.sections[0].items[0]["take"] == "hot"


def test_parse_garbage_falls_back():
    s = summarize_mod.parse_summary_response("no json here", [_item(type="sports")])
    assert s.generated is False
    assert s.sections[0].heading == "SPORTS"


def test_parse_empty_sections_falls_back():
    s = summarize_mod.parse_summary_response('{"sections":[]}', [_item()])
    assert s.generated is False


def test_fallback_groups_by_type_and_truncates_take():
    long_snippet = "x" * 500
    items = [
        _item(url="a", type="ai", snippet=long_snippet),
        _item(url="b", type="sports"),
        _item(url="c", type="ai"),
    ]
    s = summarize_mod.parse_summary_response("garbage", items)
    headings = {sec.heading: len(sec.items) for sec in s.sections}
    assert headings == {"AI": 2, "SPORTS": 1}
    ai_section = next(sec for sec in s.sections if sec.heading == "AI")
    assert len(ai_section.items[0]["take"]) == summarize_mod._FALLBACK_TAKE_MAX


def test_summarize_items_empty_returns_empty_summary():
    s = summarize_mod.summarize_items([], _settings(key="sk-x"))
    assert s.sections == [] and s.generated is False


def test_summarize_items_without_api_key_falls_back(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("must not construct a client without a key")

    monkeypatch.setattr(summarize_mod.anthropic, "Anthropic", boom)
    s = summarize_mod.summarize_items([_item()], _settings(key=None))
    assert s.generated is False


def _fake_client(text, in_tok=100, out_tok=50):
    resp = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
    )
    messages = SimpleNamespace(create=lambda **_kwargs: resp)
    return SimpleNamespace(messages=messages)


def test_summarize_items_logs_usage_once(monkeypatch):
    calls = []
    monkeypatch.setattr(
        summarize_mod.anthropic,
        "Anthropic",
        lambda **_k: _fake_client('{"sections":[{"heading":"AI","items":[]}]}'),
    )
    store = SimpleNamespace(log_usage=lambda **kw: calls.append(kw))
    s = summarize_mod.summarize_items([_item()], _settings(key="sk-x"), usage_store=store)
    assert s.generated is True
    assert len(calls) == 1
    assert calls[0]["usage_type"] == "feed_summary"
    assert calls[0]["model"] == "claude-haiku-4-5"
    assert calls[0]["input_tokens"] == 100 and calls[0]["output_tokens"] == 50
    assert calls[0]["cost_usd"] > 0


def test_summarize_items_llm_error_falls_back_without_logging_usage(monkeypatch):
    def create(**_kwargs):
        raise RuntimeError("api down")

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    monkeypatch.setattr(summarize_mod.anthropic, "Anthropic", lambda **_k: client)
    calls = []
    store = SimpleNamespace(log_usage=lambda **kw: calls.append(kw))
    s = summarize_mod.summarize_items([_item()], _settings(key="sk-x"), usage_store=store)
    assert s.generated is False
    assert calls == []


def test_summarize_items_empty_content_falls_back(monkeypatch):
    resp = SimpleNamespace(content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_k: resp))
    monkeypatch.setattr(summarize_mod.anthropic, "Anthropic", lambda **_k: client)
    s = summarize_mod.summarize_items([_item()], _settings(key="sk-x"))
    assert s.generated is False
