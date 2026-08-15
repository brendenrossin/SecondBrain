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
    cfg = parse_feed_config("not: [valid: yaml: at all")
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
