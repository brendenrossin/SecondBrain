"""Spec 001 — Feature: recall endpoint."""

import json
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from secondbrain.api import dependencies as deps
from secondbrain.api import recall as recall_module
from secondbrain.api.recall import _ReadOnlyLexicalStore, router
from secondbrain.config import Settings
from tests.fixtures.recall.index import FIXTURE_VAULT, TEST_QUERY, RecallIndex

ADR_OVERRIDES = "Witt/Projects/witt/decisions/ADR-001-overrides.md"
HARNESS = "Witt/Projects/witt/specs/001-harness.md"
SCRATCH = "Witt/Projects/witt/scratch.md"
TOOLS_SPEC = "Witt/Projects/witt-tools/specs/x.md"
SB_ADR = "Witt/Projects/second-brain/decisions/ADR-001-thin.md"
SB_HUB = "Witt/Projects/second-brain/second-brain.md"
LEARNING = "Witt/Learnings/pin-the-docstring.md"
OUTSIDE = "10_Notes/review-process.md"
ALL_WITT = {ADR_OVERRIDES, HARNESS, SCRATCH, TOOLS_SPEC, SB_ADR, SB_HUB, LEARNING}


class RecallEnv:
    """A recall app wired to one index and one Settings, plus its recall log."""

    def __init__(self, index: RecallIndex, settings: Settings) -> None:
        self.index = index
        self.settings = settings
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides = {
            deps.get_settings: lambda: settings,
            deps.get_vector_store: lambda: index.vector_store,
            deps.get_lexical_store: lambda: index.lexical_store,
            deps.get_embedder: lambda: index.embedder,
        }
        self.client = TestClient(app)

    @property
    def log_path(self) -> Path:
        return Path(self.settings.data_path) / "recall_log.jsonl"

    def log_lines(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text().splitlines()]

    def post(self, body: dict | None = None, **kwargs):
        return self.client.post("/api/v1/recall", json=body or {"query": TEST_QUERY}, **kwargs)


@pytest.fixture
def make_env(recall_index, tmp_path):
    """make_env(index=None, **settings) -> RecallEnv over the session index by default."""

    def make(index: RecallIndex | None = None, **overrides) -> RecallEnv:
        data = tmp_path / "data"
        data.mkdir(exist_ok=True)
        values = {"vault_path": FIXTURE_VAULT, "data_path": data} | overrides
        return RecallEnv(index or recall_index, Settings(_env_file=None, **values))

    return make


@pytest.fixture
def env(make_env) -> RecallEnv:
    return make_env()


def hit_paths(resp) -> list[str]:
    return [h["note_path"] for h in resp.json()["hits"]]


# --- 5.1 request validation -------------------------------------------------------

_ELEVEN = [f"Witt/{c}.md" for c in "abcdefghijk"]


@pytest.mark.parametrize(
    ("body", "field", "detail"),
    [
        ({}, "query", "missing"),
        ({"query": ""}, "query", "at least 1"),
        ({"query": "   "}, "query", "query must contain a letter or digit"),
        ({"query": "***"}, "query", "query must contain a letter or digit"),
        ({"query": "a" * 2001}, "query", "at most 2000"),
        ({"query": "x", "limit": 0}, "limit", "greater than or equal to 1"),
        ({"query": "x", "limit": 21}, "limit", "less than or equal to 20"),
        ({"query": "x", "bogus": 1}, "bogus", "extra"),
        ({"query": "x", "filters": {"bogus": 1}}, "bogus", "extra"),
        ({"query": "x", "filters": {"kinds": []}}, "kinds", "at least 1"),
        (
            {"query": "x", "filters": {"kinds": ["log"]}},
            "kinds",
            "'spec', 'decision', 'learning', 'project' or 'other'",
        ),
        ({"query": "x", "filters": {"scope": "vault"}}, "scope", "extra"),
        ({"query": "x", "filters": {"project": ""}}, "project", "pattern"),
        ({"query": "x", "filters": {"project": "Second Brain"}}, "project", "pattern"),
        (
            {"query": "x", "filters": {"exclude_paths": ["10_Notes/a.md"]}},
            "exclude_paths",
            "exclude_paths entries must start with 'Witt/'",
        ),
        ({"query": "x", "filters": {"exclude_paths": _ELEVEN}}, "exclude_paths", "at most 10"),
    ],
)
def test_invalid_requests_rejected_with_specific_messages(env, body, field, detail):
    """Scenario: invalid requests are rejected with specific messages."""
    resp = env.client.post("/api/v1/recall", json=body)

    assert resp.status_code == 422
    errors = resp.json()["detail"]
    assert any(field in err["loc"] for err in errors)
    assert detail in json.dumps(errors)
    assert env.log_lines() == []


@pytest.mark.parametrize(
    "body",
    [
        {"query": "a" * 2000},
        {"query": "x", "limit": 1},
        {"query": "x", "limit": 20},
        {"query": "x", "filters": {"exclude_paths": _ELEVEN[:10]}},
        {"query": "日本"},
    ],
)
def test_boundary_values_are_accepted(env, body):
    """Scenario: boundary values are accepted."""
    assert env.post(body).status_code == 200


# --- 5.2 pipeline steps 1-4 -------------------------------------------------------


@pytest.fixture
def spies(recall_index):
    """Spies on the recall retrieval call and the shared embedder's embed_single."""
    embedder = recall_index.embedder
    with (
        patch.object(recall_module, "_retrieve", wraps=recall_module._retrieve) as retrieve,
        patch.object(embedder, "embed_single", wraps=embedder.embed_single) as embed_single,
    ):
        yield retrieve, embed_single


def test_non_local_embedder_is_refused(make_env, spies):
    """Scenario: a non-local embedder is refused."""
    retrieve, embed_single = spies
    env = make_env(embedding_provider="openai")

    resp = env.post()

    assert resp.status_code == 503
    assert resp.json() == {"detail": "recall unavailable: requires the local embedder"}
    retrieve.assert_not_called()
    embed_single.assert_not_called()
    [line] = env.log_lines()
    assert line["status"] == 503 and line["error_type"] == "EmbedderNotLocal"

    resp = env.post({"query": TEST_QUERY, "filters": {"project": "no-such-slug"}})
    assert resp.status_code == 503
    assert resp.json()["detail"] == "recall unavailable: requires the local embedder"


def test_unknown_project_slug_short_circuits_with_a_warning(env, spies):
    """Scenario: unknown project slug short-circuits with a warning."""
    retrieve, embed_single = spies

    resp = env.post({"query": TEST_QUERY, "filters": {"project": "secondbrain"}})

    assert resp.status_code == 200
    body = resp.json()
    assert body["hits"] == []
    assert body["warnings"] == [
        "unknown project 'secondbrain'; known: second-brain, witt, witt-tools"
    ]
    retrieve.assert_not_called()
    embed_single.assert_not_called()
    assert [line["status"] for line in env.log_lines()] == [200]


@pytest.mark.parametrize("vault_path", [None, Path("/nonexistent/vault/for/recall/tests")])
def test_project_check_is_advisory_when_vault_path_missing(make_env, vault_path):
    """Scenario: project check is advisory when the vault path is missing."""
    env = make_env(vault_path=vault_path)

    resp = env.post({"query": TEST_QUERY, "filters": {"project": "witt"}})

    assert resp.status_code == 200
    body = resp.json()
    assert "vault path missing or not configured; project slug not verified" in body["notices"]
    assert body["warnings"] == []
    assert hit_paths(resp)
    assert all(p.startswith(("Witt/Projects/witt/", "Witt/Learnings/")) for p in hit_paths(resp))


def test_no_witt_projects_directory_gives_empty_known_list(make_env, tmp_path):
    """Scenario: no Witt/Projects directory gives an empty known list."""
    vault = tmp_path / "bare-vault"
    (vault / "Witt" / "Learnings").mkdir(parents=True)
    env = make_env(vault_path=vault)

    resp = env.post({"query": TEST_QUERY, "filters": {"project": "witt"}})

    assert resp.json()["warnings"] == ["unknown project 'witt'; known: none"]


def test_empty_witt_index_returns_no_hits_cleanly(make_env, tmp_path, spies):
    """Scenario: an empty Witt index returns no hits cleanly."""
    from tests.fixtures.recall.index import build_index, note, write_vault

    retrieve, _ = spies
    vault = write_vault(
        tmp_path / "v",
        {f"10_Notes/n{i}.md": note(f"N{i}", 0.8, "review process") for i in range(3)},
    )
    index = build_index(vault, tmp_path / "idx")
    assert index.lexical_store.count() == 3
    env = make_env(index=index)

    resp = env.post()

    assert resp.status_code == 200
    body = resp.json()
    assert (body["hits"], body["warnings"], body["notices"], body["witt_chunk_count"]) == (
        [],
        [],
        ["no Witt notes indexed yet"],
        0,
    )
    retrieve.assert_not_called()
    [line] = env.log_lines()
    assert line["witt_chunk_count"] == 0 and line["k_vec"] == 30


# --- 5.3 retrieval, filtering, ranking --------------------------------------------


def _build(tmp_path, notes: dict[str, str]) -> RecallIndex:
    from tests.fixtures.recall.index import build_index, write_vault

    root = tmp_path / f"vault{len(list(tmp_path.iterdir()))}"
    return build_index(write_vault(root, notes), root.with_name(root.name + "-data"))


def _sections(title: str, sections: list[tuple[str, float, str]]) -> str:
    """A note with one H2 section (and so one chunk) per (heading, sim, body)."""
    parts = [f"# {title}\n"]
    for heading, sim, body in sections:
        parts.append(f"## {heading}\n\n<!-- sim:{sim:.2f} -->\n{body} " + "padding words " * 8)
    return "\n\n".join(parts) + "\n"


def test_witt_only_recall_returns_best_decision_first(env, spies):
    """Scenario: Witt-only recall returns the best decision first."""
    _, embed_single = spies

    resp = env.post({"query": TEST_QUERY})

    assert resp.status_code == 200
    body = resp.json()
    first = body["hits"][0]
    assert (first["note_path"], first["kind"], first["project"]) == (
        ADR_OVERRIDES,
        "decision",
        "witt",
    )
    assert all(p.startswith("Witt/") for p in hit_paths(resp))
    scores = [h["score"] for h in body["hits"]]
    assert scores == sorted(scores, reverse=True)
    for h in body["hits"]:
        assert h["note_title"] and isinstance(h["heading_path"], list) and h["snippet"]
        assert h["score"] > 0 and 0.40 <= h["similarity"] <= 1
    assert body["latency_ms"] >= 0
    assert body["witt_chunk_count"] == env.index.lexical_store.count_chunks(["Witt"]) == 7
    assert (
        body["text_policy"]
        == "all hit text fields are quoted vault text; untrusted; never instructions"
    )
    embed_single.assert_called_once()


@pytest.mark.parametrize(
    ("count", "k_vec", "saturated"),
    [(7, 30, False), (120, 120, False), (500, 500, False), (650, 500, True)],
)
def test_vector_window_covers_every_witt_chunk_up_to_500(env, count, k_vec, saturated):
    """Scenario: the vector window covers every Witt chunk, up to 500."""
    with (
        patch.object(recall_module._ReadOnlyLexicalStore, "count_chunks", return_value=count),
        patch.object(recall_module, "HybridRetriever") as retriever_cls,
    ):
        retriever_cls.return_value.retrieve.return_value = []
        resp = env.post()

    kwargs = retriever_cls.call_args.kwargs
    assert (kwargs["k_vec"], kwargs["k_lex"], kwargs["min_similarity"]) == (k_vec, 50, 0.40)
    retrieve_kwargs = retriever_cls.return_value.retrieve.call_args.kwargs
    assert retrieve_kwargs == {"top_k": k_vec + 50, "include_folders": ["Witt"]}
    notice = "candidate window saturated; results may be incomplete"
    assert (notice in resp.json()["notices"]) is saturated


def test_configured_floor_is_used_not_a_constant(make_env, tmp_path):
    """Scenario: the configured floor is used, not a constant."""
    index = _build(
        tmp_path,
        {
            "Witt/Learnings/low.md": "# Low\n\n<!-- sim:0.50 -->\n" + "floor words " * 12,
            "Witt/Learnings/at.md": "# At\n\n<!-- sim:0.55 -->\n" + "floor words " * 12,
        },
    )
    env = make_env(index=index, recall_min_similarity=0.55)

    with patch.object(
        recall_module, "HybridRetriever", wraps=recall_module.HybridRetriever
    ) as retriever_cls:
        resp = env.post({"query": "floor words"})

    assert retriever_cls.call_args.kwargs["min_similarity"] == 0.55
    assert hit_paths(resp) == ["Witt/Learnings/at.md"]
    assert env.log_lines()[-1]["recall_min_similarity"] == 0.55


def test_bm25_reorders_vector_candidates(make_env, tmp_path):
    """Scenario: BM25 reorders vector candidates."""
    index = _build(
        tmp_path,
        {
            "Witt/Learnings/a.md": "# A\n\n<!-- sim:0.80 -->\n" + "plain words here " * 8,
            "Witt/Learnings/b.md": "# B\n\n<!-- sim:0.70 -->\nquokka " + "other words " * 10,
        },
    )
    resp = make_env(index=index).post({"query": "quokka"})

    a, b = sorted(resp.json()["hits"], key=lambda h: h["note_path"])
    assert hit_paths(resp)[0] == "Witt/Learnings/b.md"
    assert b["score"] > a["score"] and a["similarity"] > b["similarity"]


def test_limit_counts_notes_not_chunks(make_env, tmp_path):
    """Scenario: limit counts notes, not chunks.

    ADR-001-overrides has 5 chunks that outrank every other chunk; its highest-similarity
    chunk (0.99, no keyword match) is not its highest-RRF chunk (0.97 + lexical rank 1).
    """
    adr = _sections(
        "Overrides",
        [
            ("Top cosine", 0.99, "nothing lexical in this one"),
            ("Top rrf", 0.97, "quokka quokka quokka quokka"),
            ("Three", 0.96, "quokka quokka quokka"),
            ("Four", 0.95, "quokka quokka"),
            ("Five", 0.94, "quokka"),
        ],
    )
    others = {
        f"Witt/Projects/witt/specs/s{i}.md": f"# S{i}\n\n<!-- sim:0.{60 + i}0 -->\n"
        + "plain filler words " * 8
        for i in range(4)
    }
    index = _build(tmp_path, {ADR_OVERRIDES: adr, **others})
    resp = make_env(index=index).post({"query": "quokka", "limit": 3})

    hits = resp.json()["hits"]
    assert len(hits) == 3 and len({h["note_path"] for h in hits}) == 3
    assert hits[0]["note_path"] == ADR_OVERRIDES
    assert hits[0]["heading_path"][-1] == "Top rrf"
    assert hits[0]["snippet"].startswith("<!-- sim:0.97 -->")
    assert hits[0]["similarity"] == pytest.approx(0.97, abs=1e-4)


def test_kinds_filter_fills_the_limit_from_deep_in_the_ranking(make_env, tmp_path):
    """Scenario: a kinds filter fills the limit from deep in the ranking."""
    notes = {
        f"Witt/Projects/witt/specs/s{i}.md": f"# S{i}\n\n<!-- sim:0.9{i % 10} -->\n"
        + "deep words " * 12
        for i in range(6)
    }
    notes |= {"Witt/Projects/witt/witt.md": "# Hub\n\n<!-- sim:0.89 -->\n" + "deep words " * 12}
    notes |= {
        f"Witt/Projects/witt/misc{i}.md": f"# M{i}\n\n<!-- sim:0.8{i} -->\n" + "deep words " * 12
        for i in range(5)
    }
    notes |= {
        f"Witt/Projects/witt/decisions/d{i}.md": f"# D{i}\n\n<!-- sim:0.5{i} -->\n" + "plain " * 25
        for i in range(3)
    }
    index = _build(tmp_path, notes)
    env = make_env(index=index)
    assert all(
        h["kind"] != "decision"
        for h in env.post({"query": "deep words", "limit": 12}).json()["hits"]
    )

    resp = env.post({"query": "deep words", "filters": {"kinds": ["decision"]}, "limit": 2})

    hits = resp.json()["hits"]
    assert len(hits) == 2 and {h["kind"] for h in hits} == {"decision"}


def test_kinds_filter_keeps_matching_kinds_and_drops_the_rest(env):
    """Scenario: kinds filter keeps matching kinds and drops the rest."""
    resp = env.post({"query": TEST_QUERY, "filters": {"kinds": ["spec"]}})
    assert set(hit_paths(resp)) == {HARNESS, TOOLS_SPEC}


def test_project_filter_keeps_the_project_directory_plus_learnings(env):
    """Scenario: project filter keeps the whole project directory plus learnings."""
    resp = env.post({"query": TEST_QUERY, "filters": {"project": "second-brain"}})
    body = resp.json()
    assert set(hit_paths(resp)) == {SB_ADR, SB_HUB, LEARNING}
    assert body["warnings"] == [] and body["notices"] == []


def test_project_filter_does_not_match_a_prefix_sibling(env):
    """Scenario: project filter does not match a prefix sibling."""
    resp = env.post({"query": TEST_QUERY, "filters": {"project": "witt"}})
    hits = {h["note_path"]: h for h in resp.json()["hits"]}
    assert hits[SCRATCH]["kind"] == "other" and hits[SCRATCH]["project"] is None
    assert not any(
        p.startswith(("Witt/Projects/witt-tools/", "Witt/Projects/second-brain/")) for p in hits
    )


def test_project_and_kinds_intersect(env):
    """Scenario: project and kinds intersect."""
    resp = env.post({"query": TEST_QUERY, "filters": {"project": "witt", "kinds": ["decision"]}})
    assert hit_paths(resp) == [ADR_OVERRIDES]


def test_exclude_paths_drops_a_note_before_dedupe(env):
    """Scenario: exclude_paths drops a note before dedupe."""
    resp = env.post({"query": TEST_QUERY, "filters": {"exclude_paths": [ADR_OVERRIDES]}})
    assert ADR_OVERRIDES not in hit_paths(resp)
    assert len(hit_paths(resp)) == 5  # limit still filled from the 6 remaining Witt notes

    case_variant = "Witt/Projects/witt/decisions/adr-001-overrides.md"
    resp = env.post({"query": TEST_QUERY, "filters": {"exclude_paths": [case_variant]}})
    assert ADR_OVERRIDES in hit_paths(resp)


def test_floor_admits_vector_candidates_and_drops_keyword_only(make_env, tmp_path):
    """Scenario: the floor admits vector candidates and drops keyword-only ones."""
    index = _build(
        tmp_path,
        {
            "Witt/Learnings/hi.md": "# Hi\n\n<!-- sim:0.62 -->\n" + "general words " * 10,
            "Witt/Learnings/at.md": "# At\n\n<!-- sim:0.40 -->\n" + "general words " * 10,
            "Witt/Learnings/kw.md": "# Kw\n\n<!-- sim:0.10 -->\nquokka " + "other words " * 10,
        },
    )
    env = make_env(index=index)

    resp = env.post({"query": "quokka"})

    assert set(hit_paths(resp)) == {"Witt/Learnings/hi.md", "Witt/Learnings/at.md"}
    assert env.log_lines()[-1]["dropped_keyword_only"] == 1


def test_out_of_scope_candidates_dropped_even_if_a_store_misbehaves(env, caplog):
    """Scenario: out-of-scope candidates are dropped even if a store misbehaves."""
    from secondbrain.retrieval.hybrid import HybridRetriever

    class IgnoresFolders(HybridRetriever):
        def retrieve(self, query, top_k=10, *, include_folders=None):  # noqa: ARG002
            return super().retrieve(query, top_k)

    with patch.object(recall_module, "HybridRetriever", IgnoresFolders), caplog.at_level("WARNING"):
        resp = env.post()

    assert OUTSIDE not in hit_paths(resp)
    assert any(OUTSIDE in r.getMessage() for r in caplog.records if r.levelname == "WARNING")
    assert env.log_lines()[-1]["dropped_out_of_scope"] == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a" * 100, "a" * 100),
        ("b" * 600, "b" * 600),
        ("word " * 200, "word " * 119 + "word"),
        ("c" * 700, "c" * 600),
    ],
)
def test_snippets_truncated_on_a_word_boundary(env, text, expected):
    """Scenario: snippets are truncated on a word boundary."""
    from secondbrain.retrieval.hybrid import RetrievalCandidate

    candidate = RetrievalCandidate(
        chunk_id="c1",
        note_path=LEARNING,
        note_title="T",
        heading_path=[],
        chunk_text=text,
        similarity_score=0.6,
        bm25_score=0.0,
        rrf_score=0.01,
    )
    with patch.object(recall_module, "HybridRetriever") as retriever_cls:
        retriever_cls.return_value.retrieve.return_value = [candidate]
        resp = env.post()

    snippet = resp.json()["hits"][0]["snippet"]
    assert snippet == expected and len(snippet) <= 600


def test_applied_filters_are_echoed(env):
    """Scenario: applied filters are echoed."""
    resp = env.post({"query": TEST_QUERY, "filters": {"project": "witt"}})
    assert resp.json()["applied_filters"] == {
        "project": "witt",
        "kinds": None,
        "exclude_paths": None,
    }


# --- 5.4 recall log, request ids, 503s --------------------------------------------

DECISION_9_KEYS = {
    "ts", "request_id", "status", "error_type",
    "query", "filters", "limit",
    "recall_min_similarity", "k_vec", "k_lex", "rrf_k", "witt_chunk_count",
    "hits", "dropped_keyword_only", "dropped_out_of_scope",
    "warnings", "notices", "latency_ms", "embedding_model",
}  # fmt: skip


def test_recall_log_line_has_the_full_schema(env):
    """Scenario: the recall_log line has the full schema."""
    import hashlib

    with patch.object(
        recall_module, "HybridRetriever", wraps=recall_module.HybridRetriever
    ) as retriever_cls:
        resp = env.post({"query": TEST_QUERY, "filters": {"project": "witt"}})
    body = resp.json()
    [line] = env.log_lines()

    assert set(line) == DECISION_9_KEYS
    built = retriever_cls.call_args.kwargs
    assert (line["k_vec"], line["k_lex"], line["rrf_k"], line["recall_min_similarity"]) == (
        built["k_vec"],
        built["k_lex"],
        built["rrf_k"],
        built["min_similarity"],
    )
    assert line["witt_chunk_count"] == body["witt_chunk_count"] == 7
    assert [(h["note_path"], h["score"], h["similarity"]) for h in line["hits"]] == [
        (h["note_path"], h["score"], h["similarity"]) for h in body["hits"]
    ]
    for h in line["hits"]:
        full = env.index.lexical_store.get_chunk(h["chunk_id"])
        assert full["note_path"] == h["note_path"]
        assert h["text_sha1"] == hashlib.sha1(full["chunk_text"].encode()).hexdigest()
        assert isinstance(h["bm25"], float)
    assert line["filters"] == body["applied_filters"]
    assert line["latency_ms"] >= 0
    assert line["embedding_model"] == env.index.embedder.model_name
    assert (line["status"], line["error_type"], line["request_id"]) == (
        200,
        None,
        body["request_id"],
    )


def test_recall_log_write_failure_does_not_fail_the_request(env, caplog):
    """Scenario: a recall_log write failure does not fail the request."""
    env.log_path.mkdir(parents=True)  # a directory where the file should be: open() fails

    with caplog.at_level("WARNING"):
        resp = env.post()

    assert resp.status_code == 200 and resp.json()["hits"]
    assert any("recall_log" in r.getMessage() for r in caplog.records if r.levelname == "WARNING")


def test_x_request_id_is_honoured(env):
    """Scenario: X-Request-ID is honoured."""
    import uuid

    sent = str(uuid.uuid4())
    resp = env.post(headers={"X-Request-ID": sent})
    assert resp.json()["request_id"] == sent
    assert env.log_lines()[-1]["request_id"] == sent

    minted = env.post(headers={"X-Request-ID": "not-a-uuid"}).json()["request_id"]
    assert minted != "not-a-uuid"
    uuid.UUID(minted)
    assert env.log_lines()[-1]["request_id"] == minted


class _FailingSqlConn:
    """Delegates to a real connection but raises OperationalError for matching SQL."""

    def __init__(self, real, needle: str) -> None:
        self._real, self._needle, self.failures = real, needle, 0

    def execute(self, sql, *args):
        import sqlite3

        if self._needle in sql:
            self.failures += 1
            raise sqlite3.OperationalError("database is locked at /secret/path/lexical.db")
        return self._real.execute(sql, *args)

    def close(self) -> None:
        pass


def _inject(failure: str, index: RecallIndex, stack) -> str:
    """Install one failure from the 503 table; return the exception message it carries."""
    from chromadb.errors import ChromaError

    from secondbrain.stores.vector import VectorStore

    if failure == "embedder":
        stack.enter_context(
            patch.object(
                index.embedder, "embed_single", side_effect=RuntimeError("model load failed")
            )
        )
        return "model load failed"
    if failure == "chroma":
        collection = MagicMock()
        collection.query.side_effect = ChromaError("hnsw segment /secret/path/chroma broken")
        stack.enter_context(
            patch.object(
                VectorStore, "collection", new_callable=PropertyMock, return_value=collection
            )
        )
        return "hnsw segment"
    if failure in ("fts", "count"):
        needle = "MATCH" if failure == "fts" else "COUNT(*)"
        fake = _FailingSqlConn(index.lexical_store.conn, needle)
        # Recall queries its own read-only connection (Decision 1 fallback).
        stack.enter_context(
            patch.object(
                recall_module._ReadOnlyLexicalStore,
                "conn",
                new_callable=PropertyMock,
                return_value=fake,
            )
        )
        return "database is locked"
    stack.enter_context(
        patch.object(recall_module, "classify_witt_path", side_effect=KeyError("kind-table"))
    )
    return "kind-table"


@pytest.mark.parametrize(
    ("failure", "detail"),
    [
        ("embedder", "recall unavailable: RuntimeError"),
        ("chroma", "recall unavailable: ChromaError"),
        ("fts", "recall unavailable: OperationalError"),
        ("count", "recall unavailable: OperationalError"),
        ("classify", "recall unavailable: KeyError"),
    ],
)
def test_retrieval_failures_return_503_without_leaking_internals(
    make_env, recall_index_copy, caplog, failure, detail
):
    """Scenario: retrieval failures return 503 without leaking internals."""
    from contextlib import ExitStack

    env = make_env(index=recall_index_copy)
    with ExitStack() as stack, caplog.at_level("ERROR"):
        message = _inject(failure, recall_index_copy, stack)
        resp = env.post()

    assert resp.status_code == 503
    assert resp.json() == {"detail": detail}
    assert message not in resp.text and "/" not in resp.text
    assert any(r.exc_info for r in caplog.records if r.name == "secondbrain.api.recall")
    line = env.log_lines()[-1]
    assert (line["status"], line["error_type"]) == (
        503,
        detail.removeprefix("recall unavailable: "),
    )


# --- 5.5 the real app: no LLM calls, no writes, no network ------------------------


@pytest.fixture
def main_app_env(recall_index, tmp_path):
    """The production app (secondbrain.main.app) with recall's dependencies overridden."""
    from secondbrain.main import app

    data = tmp_path / "data"
    data.mkdir()
    settings = Settings(_env_file=None, vault_path=FIXTURE_VAULT, data_path=data)
    app.dependency_overrides.update(
        {
            deps.get_settings: lambda: settings,
            deps.get_vector_store: lambda: recall_index.vector_store,
            deps.get_lexical_store: lambda: recall_index.lexical_store,
            deps.get_embedder: lambda: recall_index.embedder,
        }
    )
    try:
        yield app, data
    finally:
        app.dependency_overrides.clear()


def test_recall_makes_no_llm_calls_and_no_writes_besides_its_own_log(main_app_env):
    """Scenario: recall makes no LLM calls and no writes besides its own log."""
    from contextlib import ExitStack

    import anthropic
    import openai

    from secondbrain.retrieval.reranker import LLMReranker
    from secondbrain.stores.usage import UsageStore
    from secondbrain.synthesis.answerer import Answerer

    app, data = main_app_env
    (data / "conversations.db").write_bytes(b"conversations-sentinel")
    (data / "queries.jsonl").write_bytes(b'{"q": "sentinel"}\n')
    before = {n: (data / n).read_bytes() for n in ("conversations.db", "queries.jsonl")}
    targets = [
        (LLMReranker, "rerank"),
        (Answerer, "answer"),
        (anthropic.Anthropic, "__init__"),
        (openai.OpenAI, "__init__"),
        (UsageStore, "log_usage"),
        (deps, "get_conversation_store"),
        (deps, "get_query_logger"),
    ]
    with ExitStack() as stack:
        spies = [
            stack.enter_context(patch.object(obj, name, side_effect=AssertionError(name)))
            for obj, name in targets
        ]
        resp = TestClient(app).post("/api/v1/recall", json={"query": TEST_QUERY})

    assert resp.status_code == 200 and resp.json()["hits"]
    for spy in spies:
        spy.assert_not_called()
    assert {n: (data / n).read_bytes() for n in before} == before
    assert len((data / "recall_log.jsonl").read_text().splitlines()) == 1


async def test_recall_makes_no_network_calls_once_the_model_is_loaded(main_app_env):
    """Scenario: recall makes no network calls once the model is loaded."""
    import httpx

    app, _data = main_app_env
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("socket.socket.connect", side_effect=AssertionError("network")) as connect:
            resp = await client.post("/api/v1/recall", json={"query": TEST_QUERY})

    assert resp.status_code == 200
    connect.assert_not_called()


# --- 5.6 tracing isolation (subprocess: Traceloop.init is process-global) ---------

_REPO_ROOT = Path(__file__).resolve().parent.parent


class _Probe:
    """Runs tests.fixtures.recall.tracing_probe in a fresh interpreter."""

    def __init__(self, mode: str, tmp_path: Path, *args: str) -> None:
        import os
        import subprocess
        import sys

        env = os.environ | {"TRACELOOP_TELEMETRY": "false"}
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.fixtures.recall.tracing_probe",
                mode,
                str(tmp_path),
                *args,
            ],
            cwd=_REPO_ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    def wait_for(self, marker: str) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            if line.startswith(marker):
                return
        raise AssertionError(f"probe exited before {marker!r} (rc={self.proc.wait()})")

    def resume(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write("\n")
        self.proc.stdin.flush()

    def result(self) -> dict:
        out, _ = self.proc.communicate(timeout=120)
        assert self.proc.returncode == 0, out
        return json.loads(out.strip().splitlines()[-1])


def test_recall_writes_zero_spans_with_tracing_on(tmp_path):
    """Scenario: recall writes zero spans with tracing on."""
    probe = _Probe("inmemory", tmp_path)
    probe.wait_for("PHASE ask-done")
    probe.resume()
    result = probe.result()

    assert result["ask_status"] == 200
    assert result["ask_chroma_query_spans"] >= 1  # the exporter really receives chroma spans
    assert result["recall_status"] == 200 and result["recall_hits"] > 0
    assert result["recall_spans"] == 0


def test_recall_never_sends_anything_to_a_reachable_langfuse(tmp_path):
    """Scenario: recall never sends anything to a reachable Langfuse."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    requests: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            requests.append((self.command, self.path))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = do_POST = _answer

        def log_message(self, *_args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        probe = _Probe("langfuse", tmp_path, f"http://127.0.0.1:{server.server_port}")
        probe.wait_for("PHASE ask-done")
        trace_posts = [r for r in requests if r == ("POST", "/api/public/otel/v1/traces")]
        baseline = len(requests)
        probe.resume()
        result = probe.result()
    finally:
        server.shutdown()

    assert len(trace_posts) >= 1  # /ask really exported to the listener
    assert result["recall_status"] == 200
    assert len(requests) == baseline


def test_unreachable_langfuse_does_not_slow_startup_or_recall(tmp_path):
    """Scenario: an unreachable Langfuse does not slow startup or recall."""
    from secondbrain.tracing import _LANGFUSE_PROBE_TIMEOUT

    result = _Probe("unreachable", tmp_path, "http://10.255.255.1:3000").result()

    assert result["traceloop_init_s"] > 0
    assert result["startup_s"] - result["traceloop_init_s"] <= _LANGFUSE_PROBE_TIMEOUT + 1
    assert result["recall_status"] == 200
    assert result["recall_s"] < 1


# --- 5.7 concurrency on real stores -------------------------------------------------


async def _post_many(app_env: RecallEnv, n: int, body: dict) -> list:
    import asyncio

    import httpx

    app = app_env.client.app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await asyncio.gather(*(client.post("/api/v1/recall", json=body) for _ in range(n)))


async def test_concurrent_recalls_are_consistent_on_real_stores(make_env, recall_index_copy):
    """Scenario: concurrent recalls are consistent on real stores.

    A cold SentenceTransformerProvider whose (patched, slow) constructor must run once.
    """
    import time

    import numpy as np

    from secondbrain.indexing.embedder import Embedder, SentenceTransformerProvider
    from tests.fixtures.recall.stub_embedder import DIM

    constructed: list[str] = []

    def slow_model(name):
        constructed.append(name)
        time.sleep(0.2)
        model = MagicMock()
        model.encode.side_effect = lambda texts, **_kw: np.tile(np.eye(DIM)[0], (len(texts), 1))
        return model

    recall_index_copy.embedder = Embedder(
        provider=SentenceTransformerProvider("BAAI/bge-base-en-v1.5")
    )
    env = make_env(index=recall_index_copy)

    with patch("sentence_transformers.SentenceTransformer", side_effect=slow_model):
        responses = await _post_many(env, 8, {"query": TEST_QUERY})

    assert [r.status_code for r in responses] == [200] * 8
    hit_sets = [r.json()["hits"] for r in responses]
    assert all(h == hit_sets[0] for h in hit_sets) and hit_sets[0]
    assert len({r.json()["request_id"] for r in responses}) == 8
    lines = env.log_path.read_text().splitlines()
    assert len(lines) == 8 and all(json.loads(line)["status"] == 200 for line in lines)
    assert constructed == ["BAAI/bge-base-en-v1.5"]


async def test_recall_during_a_reindex_answers_or_fails_cleanly(make_env, tmp_path):
    """Scenario: recall during a reindex either answers or fails cleanly."""
    import shutil
    import threading

    from tests.fixtures.recall.index import FIXTURE_VAULT, build_index, note, reindex, write_vault

    vault = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    index = build_index(vault, tmp_path / "live")
    extra = {
        f"Witt/Projects/witt/specs/new{i:02d}.md": note(
            f"New {i}", 0.5 + i / 200, "review process " * 12
        )
        for i in range(40)
    }
    write_vault(vault, extra)
    serial = build_index(vault, tmp_path / "serial")
    env = make_env(index=index)

    errors: list[BaseException] = []

    def run_reindex() -> None:
        try:
            reindex(index)
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    thread = threading.Thread(target=run_reindex)
    thread.start()
    responses = await _post_many(env, 20, {"query": TEST_QUERY})
    thread.join(timeout=60)

    assert not thread.is_alive() and errors == []
    for r in responses:
        assert r.status_code in (200, 503)
        if r.status_code == 503:
            assert r.json()["detail"].startswith("recall unavailable: ")
    assert any(r.status_code == 200 for r in responses)
    assert index.lexical_store.count() == serial.lexical_store.count()
    assert index.vector_store.count() == serial.vector_store.count()
    assert index.lexical_store.count_chunks(["Witt"]) == serial.lexical_store.count_chunks(["Witt"])


def test_recall_reads_lexical_db_through_its_own_read_only_connection(env):
    """Decision 1 fallback: recall never queries the shared lexical connection."""
    import sqlite3

    shared = env.index.lexical_store
    with (
        patch.object(shared, "search", side_effect=AssertionError("shared search")),
        patch.object(shared, "count_chunks", side_effect=AssertionError("shared count")),
    ):
        assert env.post().status_code == 200

    reader = _ReadOnlyLexicalStore(shared.db_path)
    try:
        assert reader.count_chunks(["Witt"]) == 7
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.conn.execute("DELETE FROM chunks")
    finally:
        reader.close()
