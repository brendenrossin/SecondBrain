"""LLM usage tracking store for cost monitoring."""

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

    Returns 0.0 for Ollama or unknown models.
    """
    if provider == "ollama":
        return 0.0
    provider_pricing = PRICING.get(provider, {})
    rates = provider_pricing.get(model)
    if not rates:
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
    ) -> None:
        """Log a single LLM API call."""
        now = datetime.now().astimezone().isoformat()
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
        )
        sql = """
            INSERT INTO llm_usage
                (timestamp, provider, model, usage_type, input_tokens, output_tokens, cost_usd, conversation_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
