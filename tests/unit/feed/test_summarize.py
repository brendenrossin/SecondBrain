from types import SimpleNamespace

from secondbrain.feed import summarize as summarize_mod
from secondbrain.feed.models import FeedItem


def _item(url="u", title="t", type="ai", snippet="snip"):
    return FeedItem(url=url, source_label="s", type=type, title=title, snippet=snippet)


def _settings(key=None, model="claude-haiku-4-5"):
    return SimpleNamespace(anthropic_api_key=key, feed_summary_model=model)


def test_prompt_numbers_items_and_withholds_urls():
    """URLs are withheld on purpose — the model substituted snippet links when asked
    to echo them, silently losing those takes."""
    p = summarize_mod.build_summary_prompt(
        [_item(url="https://x/1", title="Agents", type="ai"), _item(url="https://x/2", title="B")]
    )
    assert "1. [ai]" in p and "2. [ai]" in p
    assert "Agents" in p
    assert "https://x/1" not in p and "https://x/2" not in p


def test_parse_valid_json():
    """Model JSON is embedded in prose; the index resolves against our items."""
    text = 'prose {"sections":[{"heading":"AI","items":[{"i":1,"take":"hot"}]}]} more'
    s = summarize_mod.parse_summary_response(text, [_item(url="u", title="t")])
    assert s.generated is True
    assert s.sections[0].heading == "AI"
    assert s.sections[0].items[0]["take"] == "hot"
    assert s.sections[0].items[0]["url"] == "u"


def test_parse_garbage_falls_back():
    s = summarize_mod.parse_summary_response("no json here", [_item(type="sports")])
    assert s.generated is False
    assert s.sections[0].heading == "SPORTS"


def test_parse_empty_sections_falls_back():
    s = summarize_mod.parse_summary_response('{"sections":[]}', [_item()])
    assert s.generated is False


def test_fallback_groups_by_type():
    items = [
        _item(url="a", type="ai", snippet="x" * 500),
        _item(url="b", type="sports"),
        _item(url="c", type="ai"),
    ]
    s = summarize_mod.parse_summary_response("garbage", items)
    headings = {sec.heading: len(sec.items) for sec in s.sections}
    assert headings == {"AI": 2, "SPORTS": 1}


def test_fallback_leaves_takes_empty_so_generated_stays_honest():
    """A snippet stored as a `take` would be persisted into `summary` and make
    the API report generated=True for a run that never reached the model."""
    s = summarize_mod.parse_summary_response("garbage", [_item(snippet="x" * 500)])
    assert s.generated is False
    assert all(i["take"] == "" for sec in s.sections for i in sec.items)


def test_summarize_items_empty_returns_empty_summary():
    s = summarize_mod.summarize_items([], _settings(key="sk-x"))
    assert s.sections == [] and s.generated is False


def test_summarize_items_without_api_key_falls_back(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("must not construct a client without a key")

    monkeypatch.setattr(summarize_mod.anthropic, "Anthropic", boom)
    s = summarize_mod.summarize_items([_item()], _settings(key=None))
    assert s.generated is False


def _fake_client(text, in_tok=100, out_tok=50, created=None):
    """Records every messages.create call so the one-call guarantee can be asserted."""
    resp = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
        stop_reason="end_turn",
    )
    log = created if created is not None else []

    def create(**kwargs):
        log.append(kwargs)
        return resp

    return SimpleNamespace(messages=SimpleNamespace(create=create))


def test_summarize_items_logs_usage_once(monkeypatch):
    calls = []
    created = []
    monkeypatch.setattr(
        summarize_mod.anthropic,
        "Anthropic",
        lambda **_k: _fake_client(
            '{"sections":[{"heading":"AI","items":[{"i":1,"take":"t"}]}]}', created=created
        ),
    )
    store = SimpleNamespace(log_usage=lambda **kw: calls.append(kw))
    s = summarize_mod.summarize_items([_item()], _settings(key="sk-x"), usage_store=store)
    assert s.generated is True
    assert len(calls) == 1
    assert calls[0]["usage_type"] == "feed_summary"
    assert calls[0]["model"] == "claude-haiku-4-5"
    assert calls[0]["input_tokens"] == 100 and calls[0]["output_tokens"] == 50
    assert calls[0]["cost_usd"] > 0
    assert len(created) == 1  # cost discipline: exactly one LLM call per refresh


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


class TestCostDiscipline:
    """Exactly one Anthropic call per refresh — the ticket's hard constraint."""

    def test_no_retry_on_a_failed_call(self, monkeypatch):
        created = []

        def create(**kwargs):
            created.append(kwargs)
            raise RuntimeError("api down")

        client = SimpleNamespace(messages=SimpleNamespace(create=create))
        monkeypatch.setattr(summarize_mod.anthropic, "Anthropic", lambda **_k: client)
        s = summarize_mod.summarize_items([_item()], _settings(key="sk-x"))
        assert s.generated is False
        assert len(created) == 1  # failed once, did not retry

    def test_no_call_at_all_without_items_or_key(self, monkeypatch):
        created = []
        monkeypatch.setattr(
            summarize_mod.anthropic,
            "Anthropic",
            lambda **_k: _fake_client("{}", created=created),
        )
        summarize_mod.summarize_items([], _settings(key="sk-x"))
        summarize_mod.summarize_items([_item()], _settings(key=None))
        assert created == []

    def test_prompt_is_bounded_by_snippet_cap(self):
        item = _item(snippet="x" * 5000)
        prompt = summarize_mod.build_summary_prompt([item])
        assert len(prompt) < 5000  # snippet trimmed before it reaches the model


class TestPartialResponses:
    def test_truncated_json_falls_back(self):
        """max_tokens truncation lands mid-object; must not raise."""
        truncated = '{"sections":[{"heading":"AI","items":[{"url":"u","title":"t","ta'
        s = summarize_mod.parse_summary_response(truncated, [_item()])
        assert s.generated is False

    def test_items_the_model_omits_simply_get_no_take(self):
        items = [_item(url="a"), _item(url="b")]
        text = '{"sections":[{"heading":"AI","items":[{"i":1,"take":"hot"}]}]}'
        s = summarize_mod.parse_summary_response(text, items)
        assert s.generated is True
        returned = {i["url"] for sec in s.sections for i in sec.items}
        assert returned == {"a"}  # "b" is absent, not fabricated


class TestIndexResolution:
    """Items are keyed by index, and url/title always come from our own data."""

    def test_url_and_title_come_from_our_items_not_the_model(self):
        items = [_item(url="https://real/1", title="Real Title")]
        text = '{"sections":[{"heading":"AI","items":[{"i":1,"take":"hot","url":"https://evil","title":"Fake"}]}]}'
        s = summarize_mod.parse_summary_response(text, items)
        entry = s.sections[0].items[0]
        assert entry["url"] == "https://real/1"  # model's url ignored entirely
        assert entry["title"] == "Real Title"
        assert entry["take"] == "hot"

    def test_out_of_range_index_is_dropped(self):
        items = [_item(url="a")]
        text = '{"sections":[{"heading":"AI","items":[{"i":1,"take":"ok"},{"i":99,"take":"bad"}]}]}'
        s = summarize_mod.parse_summary_response(text, items)
        assert [i["url"] for i in s.sections[0].items] == ["a"]

    def test_repeated_index_is_used_once(self):
        items = [_item(url="a"), _item(url="b")]
        text = '{"sections":[{"heading":"AI","items":[{"i":1,"take":"x"},{"i":1,"take":"y"}]}]}'
        s = summarize_mod.parse_summary_response(text, items)
        assert len(s.sections[0].items) == 1

    def test_non_numeric_index_is_dropped(self):
        items = [_item(url="a")]
        text = '{"sections":[{"heading":"AI","items":[{"i":"not-a-number","take":"x"}]}]}'
        s = summarize_mod.parse_summary_response(text, items)
        assert s.generated is False  # nothing usable -> fallback

    def test_sections_with_no_usable_items_fall_back(self):
        text = '{"sections":[{"heading":"AI","items":[{"i":42,"take":"x"}]}]}'
        s = summarize_mod.parse_summary_response(text, [_item()])
        assert s.generated is False


class TestSectionOverview:
    def _parse(self, payload, items=None):
        return summarize_mod.parse_summary_response(payload, items or [_item(url="u1")])

    def test_overview_is_parsed(self):
        summary = self._parse(
            '{"sections":[{"heading":"AI","overview":"Agents everywhere.",'
            '"items":[{"i":1,"take":"hot"}]}]}'
        )
        assert summary.sections[0].overview == "Agents everywhere."

    def test_missing_overview_defaults_to_empty(self):
        summary = self._parse('{"sections":[{"heading":"AI","items":[{"i":1,"take":"hot"}]}]}')
        assert summary.sections[0].overview == ""

    def test_overview_is_trimmed(self):
        summary = self._parse(
            '{"sections":[{"heading":"AI","overview":"  spaced  ","items":[{"i":1,"take":"t"}]}]}'
        )
        assert summary.sections[0].overview == "spaced"

    def test_non_string_overview_is_coerced_not_fatal(self):
        summary = self._parse(
            '{"sections":[{"heading":"AI","overview":42,"items":[{"i":1,"take":"t"}]}]}'
        )
        assert summary.generated is True
        assert summary.sections[0].overview == "42"

    def test_fallback_sections_carry_no_overview(self):
        summary = summarize_mod._fallback([_item(url="u1")])
        assert summary.sections[0].overview == ""
        assert summary.generated is False

    def test_overview_is_capped(self):
        summary = self._parse(
            '{"sections":[{"heading":"AI","overview":"%s","items":[{"i":1,"take":"t"}]}]}'
            % ("x" * 900)
        )
        assert len(summary.sections[0].overview) == summarize_mod._OVERVIEW_MAX
