"""Tests for the UsageStore and calculate_cost."""

import logging
from datetime import UTC, datetime, timedelta
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

    def test_unknown_paid_model_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="secondbrain.stores.usage"):
            calculate_cost("anthropic", "unknown-model-xyz", 1000, 500)
        assert "Unknown model" in caplog.text
        assert "unknown-model-xyz" in caplog.text

    def test_ollama_unknown_model_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="secondbrain.stores.usage"):
            calculate_cost("ollama", "some-random-model", 1000, 500)
        assert "Unknown model" not in caplog.text


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


class TestSchemaMigration:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> UsageStore:
        return UsageStore(tmp_path / "usage.db")

    def test_observability_columns_exist(self, store: UsageStore):
        cols = {row[1] for row in store.conn.execute("PRAGMA table_info(llm_usage)").fetchall()}
        assert "trace_id" in cols
        assert "latency_ms" in cols
        assert "status" in cols
        assert "error_message" in cols

    def test_migration_is_idempotent(self, tmp_path: Path):
        store1 = UsageStore(tmp_path / "usage.db")
        store1.log_usage("anthropic", "claude-haiku-4-5", "chat_rerank", 10, 5, 0.001)
        store1.close()
        # Second init should not fail (columns already exist)
        store2 = UsageStore(tmp_path / "usage.db")
        store2.log_usage("anthropic", "claude-haiku-4-5", "chat_rerank", 10, 5, 0.001)
        assert len(store2.get_recent(limit=10)) == 2
        store2.close()

    def test_status_defaults_to_ok(self, store: UsageStore):
        store.log_usage("anthropic", "claude-haiku-4-5", "chat_rerank", 10, 5, 0.001)
        row = store.conn.execute("SELECT status FROM llm_usage").fetchone()
        assert row["status"] == "ok"


class TestLogUsageTraceFields:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> UsageStore:
        return UsageStore(tmp_path / "usage.db")

    def test_log_with_trace_fields(self, store: UsageStore):
        store.log_usage(
            "anthropic",
            "claude-haiku-4-5",
            "chat_rerank",
            100,
            50,
            0.01,
            trace_id="abc123",
            latency_ms=42.5,
            status="ok",
        )
        row = store.conn.execute(
            "SELECT trace_id, latency_ms, status, error_message FROM llm_usage"
        ).fetchone()
        assert row["trace_id"] == "abc123"
        assert abs(row["latency_ms"] - 42.5) < 0.01
        assert row["status"] == "ok"
        assert row["error_message"] is None

    def test_log_error_status(self, store: UsageStore):
        store.log_usage(
            "anthropic",
            "claude-haiku-4-5",
            "chat_rerank",
            0,
            0,
            0.0,
            trace_id="err1",
            latency_ms=100.0,
            status="error",
            error_message="Connection refused",
        )
        row = store.conn.execute("SELECT status, error_message FROM llm_usage").fetchone()
        assert row["status"] == "error"
        assert row["error_message"] == "Connection refused"

    def test_log_fallback_status(self, store: UsageStore):
        store.log_usage(
            "anthropic",
            "claude-haiku-4-5",
            "chat_rerank",
            100,
            10,
            0.001,
            trace_id="fb1",
            status="fallback",
            error_message="LLM response could not be parsed",
        )
        row = store.conn.execute("SELECT status, error_message FROM llm_usage").fetchone()
        assert row["status"] == "fallback"
        assert "parsed" in row["error_message"]


class TestGetTraces:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> UsageStore:
        s = UsageStore(tmp_path / "usage.db")
        # Insert test data with explicit timestamps and trace fields
        for i, (utype, st, ts) in enumerate(
            [
                ("chat_rerank", "ok", "2026-02-24T10:00:00"),
                ("chat_answer", "ok", "2026-02-24T10:00:01"),
                ("chat_rerank", "fallback", "2026-02-24T10:01:00"),
                ("extraction", "error", "2026-02-24T11:00:00"),
            ]
        ):
            s.conn.execute(
                "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, trace_id, latency_ms, status, error_message) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ts,
                    "anthropic",
                    "claude-haiku-4-5",
                    utype,
                    100,
                    50,
                    0.01,
                    f"trace-{i}",
                    40.0,
                    st,
                    "err" if st == "error" else None,
                ),
            )
        s.conn.commit()
        return s

    def test_get_all_traces(self, store: UsageStore):
        traces = store.get_traces(limit=10)
        assert len(traces) == 4
        # Most recent first
        assert traces[0]["usage_type"] == "extraction"

    def test_filter_by_usage_type(self, store: UsageStore):
        traces = store.get_traces(usage_type="chat_rerank")
        assert len(traces) == 2
        assert all(t["usage_type"] == "chat_rerank" for t in traces)

    def test_filter_by_status(self, store: UsageStore):
        traces = store.get_traces(status="error")
        assert len(traces) == 1
        assert traces[0]["error_message"] == "err"

    def test_filter_by_since(self, store: UsageStore):
        traces = store.get_traces(since="2026-02-24T10:30:00")
        assert len(traces) == 1
        assert traces[0]["usage_type"] == "extraction"

    def test_traces_include_all_fields(self, store: UsageStore):
        traces = store.get_traces(limit=1)
        t = traces[0]
        assert "id" in t
        assert "trace_id" in t
        assert "latency_ms" in t
        assert "status" in t
        assert "error_message" in t

    def test_limit_respected(self, store: UsageStore):
        traces = store.get_traces(limit=2)
        assert len(traces) == 2


class TestGetTraceGroup:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> UsageStore:
        s = UsageStore(tmp_path / "usage.db")
        # Two calls with the same trace_id (rerank + answer)
        s.log_usage(
            "anthropic", "claude-haiku-4-5", "chat_rerank", 100, 10, 0.001, trace_id="shared-trace"
        )
        s.log_usage(
            "anthropic", "claude-haiku-4-5", "chat_answer", 200, 100, 0.005, trace_id="shared-trace"
        )
        # Different trace_id
        s.log_usage(
            "anthropic", "claude-haiku-4-5", "chat_rerank", 50, 5, 0.0005, trace_id="other-trace"
        )
        return s

    def test_returns_correlated_calls(self, store: UsageStore):
        group = store.get_trace_group("shared-trace")
        assert len(group) == 2
        types = {g["usage_type"] for g in group}
        assert types == {"chat_rerank", "chat_answer"}

    def test_ordered_by_timestamp(self, store: UsageStore):
        group = store.get_trace_group("shared-trace")
        assert group[0]["timestamp"] <= group[1]["timestamp"]

    def test_nonexistent_trace_returns_empty(self, store: UsageStore):
        group = store.get_trace_group("does-not-exist")
        assert group == []


class TestGetAnomalies:
    @pytest.fixture()
    def store(self, tmp_path: Path) -> UsageStore:
        return UsageStore(tmp_path / "usage.db")

    def test_no_data_returns_empty(self, store: UsageStore):
        anomalies = store.get_anomalies()
        assert anomalies == []

    def test_cost_spike_detected(self, store: UsageStore):
        now = datetime.now(UTC)
        # Insert 4 days of history at $0.10/day
        for day_offset in range(4, 0, -1):
            ts = (now - timedelta(days=day_offset)).strftime("%Y-%m-%dT12:00:00")
            store.conn.execute(
                "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status) VALUES (?,?,?,?,?,?,?,?)",
                (ts, "anthropic", "claude-haiku-4-5", "chat_answer", 1000, 500, 0.10, "ok"),
            )
        # Today: $1.00 (10x average, well above 3x threshold)
        today_ts = now.strftime("%Y-%m-%dT12:00:00")
        store.conn.execute(
            "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status) VALUES (?,?,?,?,?,?,?,?)",
            (today_ts, "anthropic", "claude-haiku-4-5", "chat_answer", 10000, 5000, 1.00, "ok"),
        )
        store.conn.commit()

        anomalies = store.get_anomalies()
        cost_spikes = [a for a in anomalies if a["type"] == "cost_spike"]
        assert len(cost_spikes) == 1
        assert cost_spikes[0]["severity"] == "critical"

    def test_no_cost_spike_when_within_threshold(self, store: UsageStore):
        now = datetime.now(UTC)
        # Insert 4 days of history at $0.10/day
        for day_offset in range(4, 0, -1):
            ts = (now - timedelta(days=day_offset)).strftime("%Y-%m-%dT12:00:00")
            store.conn.execute(
                "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status) VALUES (?,?,?,?,?,?,?,?)",
                (ts, "anthropic", "claude-haiku-4-5", "chat_answer", 1000, 500, 0.10, "ok"),
            )
        # Today: $0.15 (1.5x avg, below 3x threshold)
        today_ts = now.strftime("%Y-%m-%dT12:00:00")
        store.conn.execute(
            "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status) VALUES (?,?,?,?,?,?,?,?)",
            (today_ts, "anthropic", "claude-haiku-4-5", "chat_answer", 1500, 750, 0.15, "ok"),
        )
        store.conn.commit()

        anomalies = store.get_anomalies()
        cost_spikes = [a for a in anomalies if a["type"] == "cost_spike"]
        assert len(cost_spikes) == 0

    def test_high_error_rate_detected(self, store: UsageStore):
        now = datetime.now(UTC)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S")
        # 4 errors + 1 ok = 80% error rate
        for _i in range(4):
            store.conn.execute(
                "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status, error_message) VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, "anthropic", "claude-haiku-4-5", "chat_rerank", 0, 0, 0.0, "error", "timeout"),
            )
        store.conn.execute(
            "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status) VALUES (?,?,?,?,?,?,?,?)",
            (ts, "anthropic", "claude-haiku-4-5", "chat_rerank", 100, 50, 0.01, "ok"),
        )
        store.conn.commit()

        anomalies = store.get_anomalies()
        error_anomalies = [a for a in anomalies if a["type"] == "high_error_rate"]
        assert len(error_anomalies) == 1
        assert error_anomalies[0]["severity"] == "warning"

    def test_no_error_anomaly_when_below_threshold(self, store: UsageStore):
        now = datetime.now(UTC)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S")
        # 1 error + 4 ok = 20% error rate (not above 20%)
        store.conn.execute(
            "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status, error_message) VALUES (?,?,?,?,?,?,?,?,?)",
            (ts, "anthropic", "claude-haiku-4-5", "chat_rerank", 0, 0, 0.0, "error", "timeout"),
        )
        for _ in range(4):
            store.conn.execute(
                "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status) VALUES (?,?,?,?,?,?,?,?)",
                (ts, "anthropic", "claude-haiku-4-5", "chat_rerank", 100, 50, 0.01, "ok"),
            )
        store.conn.commit()

        anomalies = store.get_anomalies()
        error_anomalies = [a for a in anomalies if a["type"] == "high_error_rate"]
        assert len(error_anomalies) == 0

    def test_high_fallback_rate_detected(self, store: UsageStore):
        now = datetime.now(UTC)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S")
        # 3 fallbacks + 1 ok = 75% fallback rate
        for _ in range(3):
            store.conn.execute(
                "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status) VALUES (?,?,?,?,?,?,?,?)",
                (ts, "anthropic", "claude-haiku-4-5", "chat_rerank", 100, 10, 0.001, "fallback"),
            )
        store.conn.execute(
            "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status) VALUES (?,?,?,?,?,?,?,?)",
            (ts, "anthropic", "claude-haiku-4-5", "chat_rerank", 100, 10, 0.001, "ok"),
        )
        store.conn.commit()

        anomalies = store.get_anomalies()
        fallback_anomalies = [a for a in anomalies if a["type"] == "high_fallback_rate"]
        assert len(fallback_anomalies) == 1

    def test_minimum_data_guards(self, store: UsageStore):
        now = datetime.now(UTC)
        ts = now.strftime("%Y-%m-%dT%H:%M:%S")
        # Only 2 error calls — below the 5-call minimum for error rate check
        for _ in range(2):
            store.conn.execute(
                "INSERT INTO llm_usage (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, status) VALUES (?,?,?,?,?,?,?,?)",
                (ts, "anthropic", "claude-haiku-4-5", "chat_rerank", 0, 0, 0.0, "error"),
            )
        store.conn.commit()

        anomalies = store.get_anomalies()
        error_anomalies = [a for a in anomalies if a["type"] == "high_error_rate"]
        assert len(error_anomalies) == 0
