"""Recall eval: labelled Witt queries against the running API (spec 001, Evals).

Measures embedder + BM25 + RRF + the sanity floor over HTTP. It never opens the stores.

    uv run python -m secondbrain.eval.recall_eval [--dataset PATH] [--base-url URL]

Exit codes: 0 all hard gates pass; 1 a gate failed; 2 the dataset is invalid;
3 the API is unreachable or returned an error.
The report goes to ``data/eval/recall-<timestamp>.json``.
"""

import argparse
import fnmatch
import hashlib
import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml

from secondbrain.config import Settings
from secondbrain.vault.connector import VaultConnector
from secondbrain.vault.witt import WITT_FOLDER

logger = logging.getLogger(__name__)

DEFAULT_DATASET = Path(__file__).parent / "recall_queries.yaml"
QUERY_KINDS = ("identifier", "short", "long", "prose")
DEFAULT_LIMIT = 5
FLOOR_MARGIN = 0.05
LATENCY_P95_MS = 1000
MRR_THRESHOLD = 0.7
RECOMMEND_CORPUS_NOTES = 15
RECOMMEND_MAX_RANK = 3
RECOMMEND_MRR_LINE = "recommend gate_mrr: true"
# Mirrors secondbrain.api.recall (importing it would load the API's store dependencies).
K_LEX = 50
RRF_K = 60

MIN_LABELLED = 8
MIN_NULL = 4
MIN_IDENTIFIER = 2
MIN_LONG = 2
LONG_CHARS = 400
VERY_LONG_CHARS = 1500
MIN_SHORT = 1
MIN_NEAR_MISS = 2

EXIT_OK, EXIT_GATE, EXIT_DATASET, EXIT_UNREACHABLE = 0, 1, 2, 3


class DatasetError(ValueError):
    """The dataset breaks a rule; the message names every reason."""


class ApiFailure(RuntimeError):
    """The recall API was unreachable or answered with an error status."""


@dataclass
class EvalQuery:
    query: str
    kind: str
    expected: str | None = None
    allowed_cohits: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    must_not_appear: list[str] = field(default_factory=list)
    near_miss: bool = False

    @property
    def labelled(self) -> bool:
        return self.expected is not None


@dataclass
class Dataset:
    queries: list[EvalQuery]
    gate_mrr: bool
    sha256: str

    @property
    def labelled(self) -> list[EvalQuery]:
        return [q for q in self.queries if q.labelled]

    @property
    def nulls(self) -> list[EvalQuery]:
        return [q for q in self.queries if not q.labelled]


# --- dataset ---------------------------------------------------------------------


def load_dataset(path: Path) -> Dataset:
    """Parse the YAML dataset. Structure only; rules are checked by validate_dataset."""
    raw = path.read_bytes()
    data = yaml.safe_load(raw) or {}
    queries = [
        EvalQuery(
            query=str(q.get("query", "")),
            kind=str(q.get("kind", "")),
            expected=q.get("expected"),
            allowed_cohits=list(q.get("allowed_cohits") or []),
            filters=dict(q.get("filters") or {}),
            must_not_appear=list(q.get("must_not_appear") or []),
            near_miss=bool(q.get("near_miss", False)),
        )
        for q in data.get("queries") or []
    ]
    return Dataset(
        queries=queries,
        gate_mrr=bool(data.get("gate_mrr", False)),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def witt_corpus(vault_path: Path) -> dict[str, str]:
    """Every indexed Witt note: vault_path/Witt/**/*.md minus DEFAULT_EXCLUDES."""
    connector = VaultConnector(vault_path)
    corpus: dict[str, str] = {}
    for rel in connector.list_notes():
        if rel.parts and rel.parts[0] == WITT_FOLDER:
            corpus[str(rel)] = (vault_path / rel).read_text(encoding="utf-8", errors="replace")
    return corpus


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def validate_dataset(dataset: Dataset, corpus: dict[str, str]) -> None:
    """Raise DatasetError naming every broken rule (spec 001 Evals, dataset validation)."""
    reasons: list[str] = []
    labelled, nulls = dataset.labelled, dataset.nulls

    def count(kind: str) -> int:
        return sum(q.kind == kind for q in labelled)

    if len(labelled) < MIN_LABELLED:
        reasons.append("too few labelled")
    if len(nulls) < MIN_NULL:
        reasons.append("too few null")
    if count("identifier") < MIN_IDENTIFIER:
        reasons.append("too few identifier")
    if sum(q.kind == "long" and len(q.query) >= LONG_CHARS for q in labelled) < MIN_LONG:
        reasons.append("too few long")
    if not any(len(q.query) >= VERY_LONG_CHARS for q in labelled):
        reasons.append("no query ≥1500 chars")
    if count("short") < MIN_SHORT:
        reasons.append("too few short")
    for key in ("project", "kinds", "exclude_paths"):
        if not any(key in q.filters for q in labelled):
            reasons.append(f"missing filter coverage: {key}")
    if sum(q.near_miss for q in nulls) < MIN_NEAR_MISS:
        reasons.append("too few near-miss")
    if any(q.kind not in QUERY_KINDS for q in dataset.queries):
        reasons.append("bad kind")
    texts = [q.query for q in dataset.queries]
    if len(set(texts)) != len(texts):
        reasons.append("duplicate query")

    notes = [_normalise(t) for t in corpus.values()]
    if any(
        q.kind in ("prose", "long") and any(_normalise(q.query) in n for n in notes)
        for q in dataset.queries
    ):
        reasons.append("verbatim query")
    if any(_normalise(term) in n for q in nulls for term in q.must_not_appear for n in notes):
        reasons.append("null contamination")

    if reasons:
        raise DatasetError("; ".join(reasons))


# --- metrics and gates -----------------------------------------------------------


def rank_of_expected(hit_paths: list[str], expected: str, allowed_cohits: list[str]) -> int | None:
    """1-based rank of expected after removing allowed co-hits; None if not returned."""
    ranked = [p for p in hit_paths if p not in allowed_cohits]
    return ranked.index(expected) + 1 if expected in ranked else None


def recall_at_1(ranks: list[int | None]) -> float:
    return sum(r == 1 for r in ranks) / len(ranks) if ranks else 0.0


def mean_reciprocal_rank(ranks: list[int | None]) -> float:
    return sum(1 / r for r in ranks if r) / len(ranks) if ranks else 0.0


def p95(values: list[float]) -> float:
    """Nearest-rank 95th percentile."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)])


def _is_excluded(path: str) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in VaultConnector.DEFAULT_EXCLUDES)


def evaluate(
    dataset: Dataset,
    responses: list[dict[str, Any]],
    *,
    vault_path: Path,
    floor: float,
    corpus_notes: int,
) -> dict[str, Any]:
    """Score responses (aligned with dataset.queries) and decide every gate."""
    per_query: list[dict[str, Any]] = []
    ranks: list[int | None] = []
    failures: dict[str, list[str]] = {}

    def fail(gate: str, why: str) -> None:
        failures.setdefault(gate, []).append(why)

    for q, resp in zip(dataset.queries, responses, strict=True):
        hits = resp.get("hits", [])
        paths = [h["note_path"] for h in hits]
        for p in paths:
            if not p.startswith(f"{WITT_FOLDER}/"):
                fail("scope_isolation", f"{q.query[:60]!r} returned {p!r}")
        row: dict[str, Any] = {"query": q.query[:120], "kind": q.kind, "hits": len(hits)}
        if q.labelled:
            assert q.expected is not None
            rank = rank_of_expected(paths, q.expected, q.allowed_cohits)
            ranks.append(rank)
            sim = next((h["similarity"] for h in hits if h["note_path"] == q.expected), None)
            row |= {"expected": q.expected, "rank_of_expected": rank, "expected_similarity": sim}
            if q.expected not in paths[:DEFAULT_LIMIT]:
                fail("expected_in_top5", f"{q.expected!r} not returned for {q.query[:60]!r}")
            elif sim is not None and sim < floor + FLOOR_MARGIN:
                fail(
                    "floor_margin",
                    f"{q.expected!r} similarity {sim:.3f} < {floor + FLOOR_MARGIN:.3f}",
                )
            if not (vault_path / q.expected).is_file() or _is_excluded(q.expected):
                fail("stale_labels", f"{q.expected!r} is not an indexed vault file")
        else:
            row["top_similarity"] = max((h["similarity"] for h in hits), default=None)
        per_query.append(row)

    latencies = [r["latency_ms"] for r in responses if isinstance(r.get("latency_ms"), int | float)]
    latency_p95 = p95(latencies)
    if len(latencies) < len(responses):
        fail("latency", f"{len(responses) - len(latencies)} responses had no latency_ms")
    if latency_p95 >= LATENCY_P95_MS:
        fail("latency", f"warm p95 {latency_p95:.0f} ms >= {LATENCY_P95_MS} ms")
    mrr = mean_reciprocal_rank(ranks)
    if dataset.gate_mrr and mrr < MRR_THRESHOLD:
        fail("mrr", f"MRR {mrr:.3f} < {MRR_THRESHOLD}")

    recommend = corpus_notes > RECOMMEND_CORPUS_NOTES or any(
        r is not None and r > RECOMMEND_MAX_RANK for r in ranks
    )
    gates = ["scope_isolation", "expected_in_top5", "floor_margin", "latency", "stale_labels"]
    if dataset.gate_mrr:
        gates.append("mrr")
    return {
        "gates": {g: {"passed": g not in failures, "failures": failures.get(g, [])} for g in gates},
        "failed_gates": sorted(failures),
        "metrics": {
            "recall_at_1": recall_at_1(ranks),
            "mrr": mrr,
            "warm_latency_p95_ms": latency_p95,
        },
        "queries": per_query,
        "recommendations": [RECOMMEND_MRR_LINE] if recommend else [],
    }


# --- running ---------------------------------------------------------------------


def _post(client: httpx.Client, url: str, body: dict[str, Any]) -> tuple[dict[str, Any], float]:
    t0 = time.perf_counter()
    try:
        resp = client.post(url, json=body)
    except httpx.TransportError as exc:
        raise ApiFailure(f"recall api unreachable at {url}: {type(exc).__name__}") from exc
    wall_ms = (time.perf_counter() - t0) * 1000
    if not resp.is_success:
        raise ApiFailure(f"recall api returned HTTP {resp.status_code}: {resp.text[:300]}")
    payload: dict[str, Any] = resp.json()
    return payload, wall_ms


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def _hf_revision(model: str) -> str | None:
    """The cached snapshot the HF hub resolves `main` to, if the model is cached."""
    hub = Path(os.environ.get("HF_HUB_CACHE") or Path.home() / ".cache/huggingface/hub")
    ref = hub / f"models--{model.replace('/', '--')}" / "refs" / "main"
    try:
        return ref.read_text().strip()
    except OSError:
        return None


def run_eval(
    dataset_path: Path,
    settings: Settings,
    client: httpx.Client,
    base_url: str,
    out_dir: Path,
) -> tuple[int, dict[str, Any]]:
    """Validate, query, score and write the report. Returns (exit code, report)."""
    url = f"{base_url}/api/v1/recall"
    # Reachability first, and it warms the embedder; not measured.
    _post(client, url, {"query": "warmup", "limit": 1})

    if settings.vault_path is None or not settings.vault_path.is_dir():
        raise DatasetError("vault path missing or not configured")
    vault_path = Path(settings.vault_path)
    dataset = load_dataset(dataset_path)
    corpus = witt_corpus(vault_path)
    validate_dataset(dataset, corpus)

    responses: list[dict[str, Any]] = []
    wall: list[float] = []
    for q in dataset.queries:
        body = {"query": q.query, "filters": q.filters, "limit": DEFAULT_LIMIT}
        payload, wall_ms = _post(client, url, body)
        responses.append(payload)
        wall.append(wall_ms)

    result = evaluate(
        dataset,
        responses,
        vault_path=vault_path,
        floor=settings.recall_min_similarity,
        corpus_notes=len(corpus),
    )
    result["metrics"]["client_wall_p95_ms"] = p95(wall)
    report: dict[str, Any] = {
        "git_sha": _git_sha(),
        "embedding_model": settings.embedding_model,
        "hf_revision": _hf_revision(settings.embedding_model),
        "k_lex": K_LEX,
        "rrf_k": RRF_K,
        "recall_min_similarity": settings.recall_min_similarity,
        "context_generation_enabled": settings.context_generation_enabled,
        "witt_chunk_count": max((r.get("witt_chunk_count") or 0 for r in responses), default=0),
        "witt_note_count": len(corpus),
        "dataset_sha256": dataset.sha256,
        "gate_mrr": dataset.gate_mrr,
        **result,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = out_dir / f"recall-{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return (EXIT_GATE if result["failed_gates"] else EXIT_OK), report


def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args(argv)

    settings = settings or Settings()
    base_url = args.base_url or f"http://{settings.host}:{settings.port}"
    out_dir = Path(settings.data_path) / "eval"
    try:
        with httpx.Client(timeout=httpx.Timeout(30.0), transport=transport) as client:
            code, report = run_eval(args.dataset, settings, client, base_url, out_dir)
    except DatasetError as exc:
        print(f"recall eval: invalid dataset: {exc}", file=sys.stderr)
        return EXIT_DATASET
    except ApiFailure as exc:
        print(f"recall eval: {exc}", file=sys.stderr)
        return EXIT_UNREACHABLE

    for line in report["recommendations"]:
        print(line, file=sys.stderr)
    for gate in report["failed_gates"]:
        print(
            f"recall eval: gate {gate} FAILED: {report['gates'][gate]['failures']}", file=sys.stderr
        )
    metrics = report["metrics"]
    print(
        f"recall eval: {'FAIL' if code else 'PASS'} — recall@1 {metrics['recall_at_1']:.2f}, "
        f"MRR {metrics['mrr']:.2f}, warm p95 {metrics['warm_latency_p95_ms']:.0f} ms; "
        f"report {report['report_path']}"
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
