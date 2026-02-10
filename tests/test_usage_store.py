"""Tests for the UsageStore and calculate_cost."""

from pathlib import Path

import pytest

from secondbrain.stores.usage import UsageStore, calculate_cost


class TestCalculateCost:
    def test_anthropic_haiku(self):
        # 1000 input tokens at $1/MTok + 500 output at $5/MTok
        cost = calculate_cost("anthropic", "claude-haiku-4-5", 1000, 500)
        expected = (1000 * 1.00 + 500 * 5.00) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_anthropic_sonnet(self):
        cost = calculate_cost("anthropic", "claude-sonnet-4-5", 10_000, 2_000)
        expected = (10_000 * 3.00 + 2_000 * 15.00) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_openai_gpt4o_mini(self):
        cost = calculate_cost("openai", "gpt-4o-mini", 5000, 1000)
        expected = (5000 * 0.15 + 1000 * 0.60) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_ollama_always_free(self):
        cost = calculate_cost("ollama", "gpt-oss:20b", 100_000, 50_000)
        assert cost == 0.0

    def test_unknown_model_returns_zero(self):
        cost = calculate_cost("anthropic", "unknown-model", 1000, 1000)
        assert cost == 0.0

    def test_unknown_provider_returns_zero(self):
        cost = calculate_cost("some-provider", "some-model", 1000, 1000)
        assert cost == 0.0


class TestUsageStore:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> UsageStore:
        return UsageStore(tmp_path / "usage.db")

    def test_schema_created(self, store: UsageStore):
        """Schema is created on first access."""
        tables = store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {row["name"] for row in tables}
        assert "llm_usage" in names

    def test_log_and_get_recent(self, store: UsageStore):
        store.log_usage("anthropic", "claude-haiku-4-5", "chat_rerank", 100, 50, 0.001)
        store.log_usage("openai", "gpt-4o-mini", "chat_answer", 200, 100, 0.0002)

        recent = store.get_recent(limit=10)
        assert len(recent) == 2
        # Most recent first
        assert recent[0]["provider"] == "openai"
        assert recent[1]["provider"] == "anthropic"

    def test_get_summary_all(self, store: UsageStore):
        store.log_usage("anthropic", "claude-haiku-4-5", "chat_rerank", 100, 50, 0.01)
        store.log_usage("anthropic", "claude-haiku-4-5", "chat_answer", 200, 100, 0.02)
        store.log_usage("openai", "gpt-4o-mini", "chat_answer", 300, 150, 0.005)

        summary = store.get_summary()
        assert summary["total_calls"] == 3
        assert abs(summary["total_cost"] - 0.035) < 1e-10
        assert "anthropic" in summary["by_provider"]
        assert summary["by_provider"]["anthropic"]["calls"] == 2
        assert "chat_rerank" in summary["by_usage_type"]
        assert "chat_answer" in summary["by_usage_type"]

    def test_get_summary_with_date_filter(self, store: UsageStore):
        # Insert with explicit timestamps
        store.conn.execute(
            "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-01-01T00:00:00", "anthropic", "claude-haiku-4-5", "chat_answer", 100, 50, 0.01),
        )
        store.conn.execute(
            "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-02-08T00:00:00", "anthropic", "claude-haiku-4-5", "chat_answer", 100, 50, 0.02),
        )
        store.conn.commit()

        # Only the Feb record should match
        summary = store.get_summary(since="2026-02-01T00:00:00")
        assert summary["total_calls"] == 1
        assert abs(summary["total_cost"] - 0.02) < 1e-10

    def test_get_daily_costs(self, store: UsageStore):
        store.conn.execute(
            "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-02-08T10:00:00", "anthropic", "claude-haiku-4-5", "chat_rerank", 100, 50, 0.01),
        )
        store.conn.execute(
            "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("2026-02-08T12:00:00", "anthropic", "claude-haiku-4-5", "chat_answer", 200, 100, 0.02),
        )
        store.conn.commit()

        daily = store.get_daily_costs(days=365)
        assert len(daily) == 1
        assert daily[0]["date"] == "2026-02-08"
        assert daily[0]["calls"] == 2
        assert abs(daily[0]["cost_usd"] - 0.03) < 1e-10

    def test_log_with_conversation_id(self, store: UsageStore):
        store.log_usage(
            "anthropic",
            "claude-haiku-4-5",
            "chat_answer",
            100,
            50,
            0.01,
            conversation_id="conv-123",
        )
        recent = store.get_recent(limit=1)
        assert recent[0]["conversation_id"] == "conv-123"

    def test_reconnect_on_error(self, store: UsageStore):
        """Verify reconnect logic doesn't crash."""
        # Force a connection then break it
        _ = store.conn
        store._reconnect()
        # Should work after reconnect
        store.log_usage("anthropic", "claude-haiku-4-5", "chat_rerank", 10, 5, 0.001)
        assert len(store.get_recent(limit=1)) == 1
