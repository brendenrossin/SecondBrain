"""Tests for OTel tracing initialization and JSONL span export."""

from secondbrain.config import Settings


def test_tracing_disabled_by_default():
    settings = Settings(
        _env_file=None,
        vault_path="/tmp/fake",
    )
    assert settings.tracing_enabled is False
