"""JSONL query logger for tracking retrieval outcomes."""

import json
from datetime import datetime
from pathlib import Path

from secondbrain.models import Citation, RetrievalLabel


class QueryLogger:
    """Logs queries and retrieval outcomes to JSONL file."""

    def __init__(self, log_path: Path) -> None:
        """Initialize the query logger.

        Args:
            log_path: Path to the JSONL log file.
        """
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_query(
        self,
        query: str,
        conversation_id: str,
        retrieval_label: RetrievalLabel,
        citations: list[Citation],
        latency_ms: float,
    ) -> None:
        """Log a query and its outcome.

        Args:
            query: The user's query.
            conversation_id: The conversation ID.
            retrieval_label: The retrieval evaluation label.
            citations: List of citations returned.
            latency_ms: Query latency in milliseconds.
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "query": query,
            "conversation_id": conversation_id,
            "retrieval_label": retrieval_label.value,
            "citation_ids": [c.chunk_id for c in citations],
            "citation_count": len(citations),
            "latency_ms": round(latency_ms, 2),
        }

        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def get_recent_queries(self, limit: int = 100) -> list[dict[str, object]]:
        """Get recent query log entries.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            List of log entries, most recent first.
        """
        if not self.log_path.exists():
            return []

        entries = []
        with self.log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # Return most recent first
        return list(reversed(entries[-limit:]))

    def get_stats(self) -> dict[str, object]:
        """Get aggregated statistics from the log.

        Returns:
            Dictionary with statistics.
        """
        entries = self.get_recent_queries(limit=10000)

        if not entries:
            return {
                "total_queries": 0,
                "label_counts": {},
                "avg_latency_ms": 0,
                "avg_citations": 0,
            }

        label_counts: dict[str, int] = {}
        total_latency = 0.0
        total_citations = 0

        for entry in entries:
            label = str(entry.get("retrieval_label", "UNKNOWN"))
            label_counts[label] = label_counts.get(label, 0) + 1
            latency_val = entry.get("latency_ms", 0)
            citation_val = entry.get("citation_count", 0)
            total_latency += float(latency_val) if latency_val else 0.0  # type: ignore[arg-type]
            total_citations += int(citation_val) if citation_val else 0  # type: ignore[call-overload]

        n = len(entries)
        return {
            "total_queries": n,
            "label_counts": label_counts,
            "avg_latency_ms": round(total_latency / n, 2) if n else 0,
            "avg_citations": round(total_citations / n, 2) if n else 0,
        }
