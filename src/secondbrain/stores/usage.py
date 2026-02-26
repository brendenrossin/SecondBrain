"""LLM usage tracking store for cost monitoring and observability."""

import contextlib
import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Pricing per million tokens (input, output)
PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {
        "claude-haiku-4-5": (1.00, 5.00),
        "claude-sonnet-4-5": (3.00, 15.00),
    },
    "openai": {
        "gpt-4o-mini": (0.15, 0.60),
    },
    "ollama": {},  # All Ollama models are free
}


def calculate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate USD cost for a given LLM call.

    Returns 0.0 for Ollama. Logs a warning for unknown paid models.
    """
    if provider == "ollama":
        return 0.0
    provider_pricing = PRICING.get(provider, {})
    rates = provider_pricing.get(model)
    if not rates:
        logger.warning(
            "Unknown model '%s/%s' — cost recorded as $0.00. "
            "Update PRICING dict in stores/usage.py.",
            provider,
            model,
        )
        return 0.0
    input_rate, output_rate = rates
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


class UsageStore:
    """SQLite-based LLM usage tracking store."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA wal_autocheckpoint=1000")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._init_schema()
        return self._conn

    def _reconnect(self) -> None:
        """Close and discard the current connection so the next access creates a fresh one."""
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                usage_type TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                conversation_id TEXT,
                metadata TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON llm_usage(timestamp);
            CREATE INDEX IF NOT EXISTS idx_usage_provider ON llm_usage(provider);
        """)
        self.conn.commit()

        # Migrate: add observability columns if they don't exist
        for _col, sql in [
            ("trace_id", "ALTER TABLE llm_usage ADD COLUMN trace_id TEXT"),
            ("latency_ms", "ALTER TABLE llm_usage ADD COLUMN latency_ms REAL"),
            ("status", "ALTER TABLE llm_usage ADD COLUMN status TEXT DEFAULT 'ok'"),
            ("error_message", "ALTER TABLE llm_usage ADD COLUMN error_message TEXT"),
        ]:
            with contextlib.suppress(sqlite3.OperationalError):
                self.conn.execute(sql)
        self.conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_usage_trace ON llm_usage(trace_id);
            CREATE INDEX IF NOT EXISTS idx_usage_status ON llm_usage(status);
            CREATE INDEX IF NOT EXISTS idx_usage_type_ts ON llm_usage(usage_type, timestamp);
        """)
        self.conn.commit()

    def log_usage(
        self,
        provider: str,
        model: str,
        usage_type: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        conversation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        trace_id: str | None = None,
        latency_ms: float | None = None,
        status: str = "ok",
        error_message: str | None = None,
    ) -> None:
        """Log a single LLM API call."""
        now = datetime.now(UTC).isoformat()
        meta_json = json.dumps(metadata) if metadata else None
        params = (
            now,
            provider,
            model,
            usage_type,
            input_tokens,
            output_tokens,
            cost_usd,
            conversation_id,
            meta_json,
            trace_id,
            latency_ms,
            status,
            error_message,
        )
        sql = """
            INSERT INTO llm_usage
                (timestamp, provider, model, usage_type, input_tokens, output_tokens,
                 cost_usd, conversation_id, metadata, trace_id, latency_ms, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            self.conn.execute(sql, params)
            self.conn.commit()
        except sqlite3.DatabaseError:
            logger.warning("UsageStore: DatabaseError on log_usage, reconnecting")
            self._reconnect()
            self.conn.execute(sql, params)
            self.conn.commit()

    def get_summary(
        self,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        """Get aggregated cost summary.

        Args:
            since: ISO timestamp lower bound (inclusive).
            until: ISO timestamp upper bound (exclusive).

        Returns:
            Dict with total_cost, total_calls, by_provider, by_usage_type.
        """
        conditions = []
        params: list[str] = []
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
        if until:
            conditions.append("timestamp < ?")
            params.append(until)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # By provider
        sql = f"""
            SELECT provider,
                   SUM(cost_usd) as cost,
                   COUNT(*) as calls,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens
            FROM llm_usage {where}
            GROUP BY provider
        """
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.DatabaseError:
            logger.warning("UsageStore: DatabaseError on get_summary, reconnecting")
            self._reconnect()
            rows = self.conn.execute(sql, params).fetchall()

        by_provider = {
            row["provider"]: {
                "cost": row["cost"] or 0.0,
                "calls": row["calls"],
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0,
            }
            for row in rows
        }

        # By usage type
        sql2 = f"""
            SELECT usage_type,
                   SUM(cost_usd) as cost,
                   COUNT(*) as calls,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens
            FROM llm_usage {where}
            GROUP BY usage_type
        """
        try:
            rows2 = self.conn.execute(sql2, params).fetchall()
        except sqlite3.DatabaseError:
            self._reconnect()
            rows2 = self.conn.execute(sql2, params).fetchall()

        by_usage_type = {
            row["usage_type"]: {
                "cost": row["cost"] or 0.0,
                "calls": row["calls"],
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0,
            }
            for row in rows2
        }

        total_cost = sum(v["cost"] for v in by_provider.values())
        total_calls = sum(v["calls"] for v in by_provider.values())

        return {
            "total_cost": total_cost,
            "total_calls": total_calls,
            "by_provider": by_provider,
            "by_usage_type": by_usage_type,
        }

    def get_daily_costs(self, days: int = 30) -> list[dict[str, Any]]:
        """Get daily cost breakdown for the last N days.

        Returns:
            List of dicts with date, cost_usd, calls, by_provider.
        """
        since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        sql = """
            SELECT DATE(timestamp) as date,
                   provider,
                   SUM(cost_usd) as cost,
                   COUNT(*) as calls
            FROM llm_usage
            WHERE timestamp >= ?
            GROUP BY DATE(timestamp), provider
            ORDER BY date ASC
        """
        try:
            rows = self.conn.execute(sql, (since,)).fetchall()
        except sqlite3.DatabaseError:
            logger.warning("UsageStore: DatabaseError on get_daily_costs, reconnecting")
            self._reconnect()
            rows = self.conn.execute(sql, (since,)).fetchall()

        # Group by date
        daily: dict[str, dict[str, Any]] = {}
        for row in rows:
            date = row["date"]
            if date not in daily:
                daily[date] = {"date": date, "cost_usd": 0.0, "calls": 0, "by_provider": {}}
            daily[date]["cost_usd"] += row["cost"] or 0.0
            daily[date]["calls"] += row["calls"]
            daily[date]["by_provider"][row["provider"]] = row["cost"] or 0.0

        return list(daily.values())

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent individual usage entries."""
        sql = """
            SELECT timestamp, provider, model, usage_type,
                   input_tokens, output_tokens, cost_usd, conversation_id
            FROM llm_usage
            ORDER BY id DESC
            LIMIT ?
        """
        try:
            rows = self.conn.execute(sql, (limit,)).fetchall()
        except sqlite3.DatabaseError:
            logger.warning("UsageStore: DatabaseError on get_recent, reconnecting")
            self._reconnect()
            rows = self.conn.execute(sql, (limit,)).fetchall()

        return [dict(row) for row in rows]

    def get_traces(
        self,
        limit: int = 50,
        usage_type: str | None = None,
        status: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent individual usage entries with full trace data."""
        conditions: list[str] = []
        params: list[Any] = []
        if usage_type:
            conditions.append("usage_type = ?")
            params.append(usage_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT id, timestamp, provider, model, usage_type,
                   input_tokens, output_tokens, cost_usd,
                   trace_id, latency_ms, status, error_message
            FROM llm_usage {where}
            ORDER BY id DESC
            LIMIT ?
        """
        params.append(limit)
        try:
            rows = self.conn.execute(sql, params).fetchall()
        except sqlite3.DatabaseError:
            logger.warning("UsageStore: DatabaseError on get_traces, reconnecting")
            self._reconnect()
            rows = self.conn.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    def get_trace_group(self, trace_id: str) -> list[dict[str, Any]]:
        """Get all calls sharing a trace_id, ordered by timestamp."""
        sql = """
            SELECT id, timestamp, provider, model, usage_type,
                   input_tokens, output_tokens, cost_usd,
                   trace_id, latency_ms, status, error_message
            FROM llm_usage
            WHERE trace_id = ?
            ORDER BY timestamp ASC
        """
        try:
            rows = self.conn.execute(sql, (trace_id,)).fetchall()
        except sqlite3.DatabaseError:
            logger.warning("UsageStore: DatabaseError on get_trace_group, reconnecting")
            self._reconnect()
            rows = self.conn.execute(sql, (trace_id,)).fetchall()

        return [dict(row) for row in rows]

    def get_anomalies(self) -> list[dict[str, Any]]:
        """Check for anomalous usage patterns. Returns list of anomaly dicts."""
        anomalies: list[dict[str, Any]] = []

        # 1. Cost spike: today > 3x 7-day daily average
        try:
            row = self.conn.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN DATE(timestamp) = DATE('now') THEN cost_usd ELSE 0 END), 0) as today_cost,
                    COALESCE(sub.avg_daily_cost, 0) as avg_daily_cost,
                    COALESCE(sub.day_count, 0) as day_count
                FROM llm_usage
                LEFT JOIN (
                    SELECT AVG(daily_cost) as avg_daily_cost, COUNT(*) as day_count
                    FROM (
                        SELECT DATE(timestamp) as d, SUM(cost_usd) as daily_cost
                        FROM llm_usage
                        WHERE DATE(timestamp) >= DATE('now', '-7 days')
                          AND DATE(timestamp) < DATE('now')
                        GROUP BY DATE(timestamp)
                    )
                ) sub ON 1=1
            """).fetchone()
            if (
                row
                and row["day_count"] >= 3
                and row["avg_daily_cost"] > 0
                and row["today_cost"] > 3 * row["avg_daily_cost"]
            ):
                anomalies.append(
                    {
                        "type": "cost_spike",
                        "severity": "critical",
                        "message": f"Today's cost (${row['today_cost']:.2f}) is {row['today_cost'] / row['avg_daily_cost']:.1f}x the 7-day average (${row['avg_daily_cost']:.2f}/day)",
                        "details": {
                            "today_cost": round(row["today_cost"], 4),
                            "avg_daily_cost": round(row["avg_daily_cost"], 4),
                        },
                    }
                )
        except sqlite3.DatabaseError:
            logger.warning("Anomaly detection: cost spike check failed")

        # 2. Call count spike per usage_type
        try:
            rows = self.conn.execute("""
                SELECT usage_type,
                    SUM(CASE WHEN DATE(timestamp) = DATE('now') THEN 1 ELSE 0 END) as today_calls,
                    sub.avg_daily_calls,
                    sub.day_count
                FROM llm_usage
                LEFT JOIN (
                    SELECT usage_type as ut, AVG(daily_calls) as avg_daily_calls, COUNT(*) as day_count
                    FROM (
                        SELECT usage_type, DATE(timestamp) as d, COUNT(*) as daily_calls
                        FROM llm_usage
                        WHERE DATE(timestamp) >= DATE('now', '-7 days')
                          AND DATE(timestamp) < DATE('now')
                        GROUP BY usage_type, DATE(timestamp)
                    )
                    GROUP BY usage_type
                ) sub ON sub.ut = llm_usage.usage_type
                WHERE DATE(timestamp) >= DATE('now', '-7 days')
                GROUP BY usage_type
            """).fetchall()
            for r in rows:
                if (
                    r["day_count"]
                    and r["day_count"] >= 3
                    and r["avg_daily_calls"]
                    and r["avg_daily_calls"] > 0
                    and r["today_calls"] > 3 * r["avg_daily_calls"]
                ):
                    anomalies.append(
                        {
                            "type": "call_spike",
                            "severity": "critical",
                            "message": f"'{r['usage_type']}' has {r['today_calls']} calls today — {r['today_calls'] / r['avg_daily_calls']:.1f}x the 7-day average ({r['avg_daily_calls']:.0f}/day)",
                            "details": {
                                "usage_type": r["usage_type"],
                                "today_calls": r["today_calls"],
                                "avg_daily_calls": round(r["avg_daily_calls"], 1),
                            },
                        }
                    )
        except sqlite3.DatabaseError:
            logger.warning("Anomaly detection: call spike check failed")

        # 3. High error rate: >20% of calls in last hour have status != 'ok'
        try:
            row = self.conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status IS NOT NULL AND status != 'ok' THEN 1 ELSE 0 END) as errors
                FROM llm_usage
                WHERE timestamp >= datetime('now', '-1 hour')
            """).fetchone()
            if row and row["total"] >= 5:
                error_rate = row["errors"] / row["total"]
                if error_rate > 0.20:
                    anomalies.append(
                        {
                            "type": "high_error_rate",
                            "severity": "warning",
                            "message": f"{row['errors']}/{row['total']} calls ({error_rate:.0%}) failed in the last hour",
                            "details": {
                                "total": row["total"],
                                "errors": row["errors"],
                                "error_rate": round(error_rate, 3),
                            },
                        }
                    )
        except sqlite3.DatabaseError:
            logger.warning("Anomaly detection: error rate check failed")

        # 4. High fallback rate: >50% of reranker calls falling back today
        try:
            row = self.conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'fallback' THEN 1 ELSE 0 END) as fallbacks
                FROM llm_usage
                WHERE usage_type = 'chat_rerank'
                  AND DATE(timestamp) = DATE('now')
            """).fetchone()
            if row and row["total"] >= 3:
                fallback_rate = row["fallbacks"] / row["total"]
                if fallback_rate > 0.50:
                    anomalies.append(
                        {
                            "type": "high_fallback_rate",
                            "severity": "warning",
                            "message": f"Reranker falling back to similarity scores on {row['fallbacks']}/{row['total']} calls today ({fallback_rate:.0%})",
                            "details": {
                                "total": row["total"],
                                "fallbacks": row["fallbacks"],
                                "fallback_rate": round(fallback_rate, 3),
                            },
                        }
                    )
        except sqlite3.DatabaseError:
            logger.warning("Anomaly detection: fallback rate check failed")

        return anomalies

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
