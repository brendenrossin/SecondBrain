"""Subprocess probe for recall's tracing isolation (spec 001 step 5.6).

``Traceloop.init`` instruments process-wide and can't be undone, so each scenario runs
here in a fresh interpreter and prints one JSON object on the last stdout line:

    python -m tests.fixtures.recall.tracing_probe inmemory <tmpdir>
    python -m tests.fixtures.recall.tracing_probe langfuse <tmpdir> <langfuse_host>
    python -m tests.fixtures.recall.tracing_probe unreachable <tmpdir> <langfuse_host>

The real ``init_tracing(settings)`` runs inside the app lifespan. ``/ask`` uses the
fixture index with mocked LLMs, so it really queries Chroma.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("TRACELOOP_TELEMETRY", "false")  # no anonymous telemetry calls


def main(mode: str, tmp: Path, langfuse_host: str = "") -> dict[str, object]:
    from fastapi.testclient import TestClient
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from traceloop.sdk import Traceloop

    from secondbrain import main as main_module
    from secondbrain import tracing
    from secondbrain.api import ask as ask_module
    from secondbrain.api import dependencies as deps
    from secondbrain.config import Settings
    from secondbrain.logging.query_logger import QueryLogger
    from secondbrain.models import RetrievalLabel
    from secondbrain.retrieval.hybrid import HybridRetriever
    from secondbrain.stores.conversation import ConversationStore
    from tests.fixtures.recall.index import FIXTURE_VAULT, TEST_QUERY, build_index

    idx = build_index(FIXTURE_VAULT, tmp / "index")
    data = tmp / "data"
    data.mkdir(parents=True, exist_ok=True)
    langfuse = {}
    if mode != "inmemory":
        langfuse = {
            "langfuse_public_key": "pk",
            "langfuse_secret_key": "sk",
            "langfuse_host": langfuse_host,
        }
    settings = Settings(
        _env_file=None, tracing_enabled=True, vault_path=FIXTURE_VAULT, data_path=data, **langfuse
    )

    reranker, answerer = MagicMock(), MagicMock()
    reranker.rerank.return_value = ([], RetrievalLabel.NO_RESULTS)
    answerer.answer.return_value = "mocked answer"
    link_expander = MagicMock()
    link_expander.expand.return_value = []
    app = main_module.app
    app.dependency_overrides.update(
        {
            deps.get_settings: lambda: settings,
            deps.get_vector_store: lambda: idx.vector_store,
            deps.get_lexical_store: lambda: idx.lexical_store,
            deps.get_embedder: lambda: idx.embedder,
            deps.get_retriever: lambda: HybridRetriever(
                idx.vector_store, idx.lexical_store, idx.embedder
            ),
            deps.get_link_expander: lambda: link_expander,
            deps.get_conversation_store: lambda: ConversationStore(data / "conversations.db"),
            deps.get_query_logger: lambda: QueryLogger(data / "queries.jsonl"),
        }
    )

    memory = InMemorySpanExporter()
    init_kwargs = {"disable_batch": True} if mode == "inmemory" else {}
    real_init = Traceloop.init
    timings: dict[str, float] = {}

    def timed_init(*args: object, **kwargs: object) -> object:
        t0 = time.perf_counter()
        try:
            return real_init(*args, **kwargs, **init_kwargs)
        finally:
            timings["traceloop_init_s"] = time.perf_counter() - t0

    patches = [
        # Timed so startup can be measured without Traceloop's own instrumentation cost;
        # in inmemory mode it also selects a SimpleSpanProcessor (spans export as they end).
        patch.object(Traceloop, "init", timed_init),
        patch.object(main_module, "get_settings", return_value=settings),
        patch.object(ask_module, "get_reranker", return_value=reranker),
        patch.object(ask_module, "get_answerer", return_value=answerer),
    ]
    if mode == "inmemory":
        patches.append(patch.object(tracing, "FileSpanExporter", lambda _dir: memory))
    for p in patches:
        p.start()

    def flush() -> None:
        trace.get_tracer_provider().force_flush()  # type: ignore[attr-defined]

    result: dict[str, object] = {}
    started = time.perf_counter()
    with TestClient(app) as client:
        result["startup_s"] = time.perf_counter() - started
        result["traceloop_init_s"] = timings.get("traceloop_init_s", 0.0)
        if mode != "unreachable":
            ask = client.post("/api/v1/ask", json={"query": TEST_QUERY})
            result["ask_status"] = ask.status_code
            flush()
            spans = memory.get_finished_spans()
            result["ask_spans"] = len(spans)
            result["ask_chroma_query_spans"] = sum(s.name == "chroma.query" for s in spans)
            memory.clear()
            print("PHASE ask-done", flush=True)
            sys.stdin.readline()  # the parent records its listener count here
        t0 = time.perf_counter()
        recall = client.post("/api/v1/recall", json={"query": TEST_QUERY})
        result["recall_s"] = time.perf_counter() - t0
        result["recall_status"] = recall.status_code
        result["recall_hits"] = len(recall.json().get("hits", []))
        flush()
        result["recall_spans"] = len(memory.get_finished_spans())
    return result


if __name__ == "__main__":
    out = main(sys.argv[1], Path(sys.argv[2]), *sys.argv[3:])
    print(json.dumps(out), flush=True)
