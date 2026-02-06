"""RAG evaluation harness for measuring retrieval quality."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from secondbrain.eval.metrics import mrr, precision_at_k, recall_at_k
from secondbrain.retrieval.hybrid import HybridRetriever, RetrievalCandidate

logger = logging.getLogger(__name__)


@dataclass
class EvalQuery:
    """A single evaluation query with ground truth."""

    query: str
    expected_notes: list[str]
    tags: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    """Result of evaluating a single query."""

    query: str
    expected: list[str]
    retrieved: list[str]
    recall_at_5: float
    recall_at_10: float
    precision_at_5: float
    mrr: float
    hits_at_5: list[str]
    misses_at_5: list[str]
    tags: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    """Aggregate evaluation report."""

    model_name: str
    timestamp: str
    num_queries: int
    avg_recall_at_5: float
    avg_recall_at_10: float
    avg_precision_at_5: float
    avg_mrr: float
    results: list[EvalResult]


def load_queries(path: Path) -> list[EvalQuery]:
    """Load evaluation queries from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return [
        EvalQuery(
            query=q["query"],
            expected_notes=q["expected_notes"],
            tags=q.get("tags", []),
        )
        for q in data["queries"]
    ]


def _dedupe_note_paths(candidates: list[RetrievalCandidate]) -> list[str]:
    """Extract unique note paths from candidates, preserving rank order."""
    seen: set[str] = set()
    paths: list[str] = []
    for c in candidates:
        if c.note_path not in seen:
            seen.add(c.note_path)
            paths.append(c.note_path)
    return paths


class RAGEvaluator:
    """Evaluates RAG retrieval quality against ground truth queries."""

    def __init__(self, retriever: HybridRetriever, top_k: int = 10) -> None:
        self.retriever = retriever
        self.top_k = top_k

    def run(self, queries: list[EvalQuery], model_name: str = "unknown") -> EvalReport:
        """Run all queries and compute aggregate metrics."""
        results: list[EvalResult] = []

        for q in queries:
            candidates = self.retriever.retrieve(q.query, top_k=self.top_k)
            retrieved_notes = _dedupe_note_paths(candidates)

            r5 = recall_at_k(q.expected_notes, retrieved_notes, 5)
            r10 = recall_at_k(q.expected_notes, retrieved_notes, 10)
            p5 = precision_at_k(q.expected_notes, retrieved_notes, 5)
            m = mrr(q.expected_notes, retrieved_notes)

            top5_set = set(retrieved_notes[:5])
            hits = [n for n in q.expected_notes if n in top5_set]
            misses = [n for n in q.expected_notes if n not in top5_set]

            results.append(
                EvalResult(
                    query=q.query,
                    expected=q.expected_notes,
                    retrieved=retrieved_notes,
                    recall_at_5=r5,
                    recall_at_10=r10,
                    precision_at_5=p5,
                    mrr=m,
                    hits_at_5=hits,
                    misses_at_5=misses,
                    tags=q.tags,
                )
            )

        n = len(results)
        report = EvalReport(
            model_name=model_name,
            timestamp=datetime.now(UTC).isoformat(),
            num_queries=n,
            avg_recall_at_5=sum(r.recall_at_5 for r in results) / n if n else 0,
            avg_recall_at_10=sum(r.recall_at_10 for r in results) / n if n else 0,
            avg_precision_at_5=sum(r.precision_at_5 for r in results) / n if n else 0,
            avg_mrr=sum(r.mrr for r in results) / n if n else 0,
            results=results,
        )
        return report


def print_report(report: EvalReport) -> None:
    """Print a human-readable evaluation report to stdout."""
    print(f"\n{'=' * 70}")
    print(f"RAG Eval Report — {report.model_name}")
    print(f"{'=' * 70}")
    print(f"Timestamp:      {report.timestamp}")
    print(f"Queries:        {report.num_queries}")
    print(f"Avg Recall@5:   {report.avg_recall_at_5:.3f}")
    print(f"Avg Recall@10:  {report.avg_recall_at_10:.3f}")
    print(f"Avg Precision@5:{report.avg_precision_at_5:.3f}")
    print(f"Avg MRR:        {report.avg_mrr:.3f}")
    print(f"{'-' * 70}")

    for r in report.results:
        status = "PASS" if r.recall_at_5 == 1.0 else "FAIL"
        print(f"\n[{status}] {r.query}")
        print(f"  Tags:       {', '.join(r.tags)}")
        print(f"  Recall@5:   {r.recall_at_5:.2f}  Recall@10: {r.recall_at_10:.2f}  "
              f"P@5: {r.precision_at_5:.2f}  MRR: {r.mrr:.2f}")
        if r.hits_at_5:
            print(f"  Hits@5:     {r.hits_at_5}")
        if r.misses_at_5:
            print(f"  Misses@5:   {r.misses_at_5}")
        print(f"  Retrieved:  {r.retrieved[:5]}")

    print(f"\n{'=' * 70}\n")


def save_report(report: EvalReport, output_dir: Path) -> Path:
    """Save the evaluation report as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    safe_model = report.model_name.replace("/", "_")
    filename = f"{safe_model}-{ts}.json"
    path = output_dir / filename
    with open(path, "w") as f:
        json.dump(asdict(report), f, indent=2)
    logger.info("Eval report saved to %s", path)
    return path
