from secondbrain.feed.config import SEED_DEFAULTS, load_feed_config, parse_feed_config


def test_parse_valid_frontmatter():
    text = """---
sources:
  - url: https://example.com/feed
    label: Example
    type: ai
    trust: 0.9
interests:
  agents: 2.0
  padres: 1.5
---
Notes below frontmatter are ignored.
"""
    cfg = parse_feed_config(text)
    assert len(cfg.sources) == 1
    assert cfg.sources[0].url == "https://example.com/feed"
    assert cfg.sources[0].trust == 0.9
    assert cfg.interests["agents"] == 2.0


def test_parse_malformed_falls_back_to_defaults():
    cfg = parse_feed_config("---\nnot: [valid: yaml: at all\n---\n")
    assert cfg.sources == SEED_DEFAULTS.sources


def test_parse_missing_keys_falls_back():
    cfg = parse_feed_config("---\nunrelated: true\n---\n")
    assert cfg.sources == SEED_DEFAULTS.sources


def test_load_missing_file_returns_defaults(tmp_path):
    cfg = load_feed_config(tmp_path, "_config/feed.md")
    assert cfg.sources == SEED_DEFAULTS.sources


def test_seed_defaults_have_both_types():
    types = {s.type for s in SEED_DEFAULTS.sources}
    assert "ai" in types and "sports" in types


def test_non_dict_interests_keeps_sources():
    text = """---
sources:
  - url: https://example.com/feed
    label: Example
    type: ai
interests:
  - 1
  - 2
---
"""
    cfg = parse_feed_config(text)
    assert len(cfg.sources) == 1
    assert cfg.sources[0].url == "https://example.com/feed"
    assert cfg.interests == {}


class TestFieldLevelResilience:
    """One bad field must degrade that field, not discard the user's whole config."""

    def _cfg(self, body):
        return parse_feed_config(f"---\n{body}\n---\n\n# Feed\n")

    def test_bad_trust_degrades_only_that_source(self):
        cfg = self._cfg(
            "sources:\n"
            "  - {url: 'https://a/f', label: A, type: ai, trust: high}\n"
            "  - {url: 'https://b/f', label: B, type: ai, trust: 0.9}\n"
        )
        assert [s.label for s in cfg.sources] == ["A", "B"]
        assert cfg.sources[0].trust == 0.5  # fell back, config kept
        assert cfg.sources[1].trust == 0.9

    def test_bad_interest_weight_drops_only_that_keyword(self):
        cfg = self._cfg(
            "sources:\n  - {url: 'https://a/f', label: A, type: ai}\n"
            "interests:\n  agents: 2.0\n  broken: not-a-number\n"
        )
        assert [s.label for s in cfg.sources] == ["A"]
        assert cfg.interests == {"agents": 2.0}

    def test_trust_is_clamped_to_unit_range(self):
        cfg = self._cfg(
            "sources:\n"
            "  - {url: 'https://a/f', label: A, type: ai, trust: -5}\n"
            "  - {url: 'https://b/f', label: B, type: ai, trust: 1000}\n"
        )
        assert [s.trust for s in cfg.sources] == [0.0, 1.0]

    def test_runaway_interest_weight_is_capped(self):
        cfg = self._cfg(
            "sources:\n  - {url: 'https://a/f', label: A, type: ai}\n"
            "interests:\n  padres: 1000000\n"
        )
        assert cfg.interests["padres"] == 10.0

    def test_source_list_is_capped(self):
        rows = "\n".join(
            f"  - {{url: 'https://s{i}/f', label: S{i}, type: ai}}" for i in range(120)
        )
        cfg = self._cfg(f"sources:\n{rows}")
        assert len(cfg.sources) == 50

    def test_genuinely_broken_yaml_still_falls_back(self):
        cfg = parse_feed_config("---\nsources: [unclosed\n---\n")
        assert cfg is SEED_DEFAULTS
