"""Spec 001 — Feature: recall eval."""

import copy
import json
import os
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
import yaml

from secondbrain.config import Settings
from secondbrain.eval import recall_eval as ev
from tests.fixtures.recall.index import write_vault

REPO_ROOT = Path(__file__).resolve().parent.parent

ADR = "Witt/Projects/p/decisions/ADR-002-overrides.md"
SPEC = "Witt/Projects/p/specs/001-layout.md"
HUB = "Witt/Projects/p/p.md"
LEARN = "Witt/Learnings/pin.md"
COHIT = "Witt/Projects/p/specs/002-mirror.md"
NOTES = {
    ADR: "# ADR-002 Overrides\n\nOverrides may skip review when they are recorded in history.\n",
    SPEC: "# Layout\n\nThe classify_witt_path function maps a path to its kind.\n",
    HUB: "# p\n\nProject hub with links to everything about the overrides policy.\n",
    LEARN: "# Pin it\n\nPin a tool description so drift shows up in review.\n",
    COHIT: "# Mirror\n\nThis spec quotes ADR-002 about overrides at length.\n",
    "10_Notes/cooking.md": "# Cooking\n\nsourdough starter feeding schedule\n",
    "Witt/Logs/2026-11-21.md": "# Log\n\ntoday I worked on things\n",
}


def _words(n: int, seed: str) -> str:
    return " ".join(f"{seed}{i}" for i in range(n))


def base_dataset() -> dict:
    """An otherwise-valid dataset over NOTES."""
    labelled = [
        {"query": "ADR-002", "kind": "identifier", "expected": ADR, "filters": {"project": "p"}},
        {"query": "classify_witt_path", "kind": "identifier", "expected": SPEC,
         "filters": {"kinds": ["spec"]}},
        {"query": "how are overrides " + _words(120, "lq"), "kind": "long", "expected": ADR,
         "filters": {"exclude_paths": [COHIT]}},
        {"query": "why we pin descriptions " + _words(400, "vl"), "kind": "long",
         "expected": LEARN},
        {"query": "overrides", "kind": "short", "expected": ADR, "allowed_cohits": [COHIT]},
        {"query": "may a spec skip its review if recorded", "kind": "prose", "expected": ADR},
        {"query": "which function decides the kind of a note", "kind": "prose", "expected": SPEC},
        {"query": "where is the project overview kept", "kind": "prose", "expected": HUB},
    ]  # fmt: skip
    nulls = [
        {"query": "best espresso grinder", "kind": "prose", "must_not_appear": ["espresso"],
         "near_miss": True},
        {"query": "kubernetes pod autoscaling", "kind": "prose", "must_not_appear": ["kubernetes"],
         "near_miss": True},
        {"query": "marathon training plan", "kind": "prose", "must_not_appear": ["marathon"]},
        {"query": "tax deadline for llcs", "kind": "prose", "must_not_appear": ["llc"]},
    ]  # fmt: skip
    return {"queries": labelled + nulls}


def _hit(path: str, sim: float = 0.8) -> dict:
    return {"note_path": path, "similarity": sim, "score": 0.03, "kind": "other"}


Responder = Callable[[dict], dict]


def perfect(body: dict, dataset: dict) -> dict:
    """Expected note at rank 1 (sim 0.8) for labelled queries; [] for nulls."""
    q = next((q for q in dataset["queries"] if q["query"] == body["query"]), None)
    hits = [_hit(q["expected"])] if q and q.get("expected") else []
    return {"hits": hits, "latency_ms": 20, "witt_chunk_count": 9}


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.vault = write_vault(tmp_path / "vault", NOTES)
        self.data = tmp_path / "data"
        self.dataset_path = tmp_path / "queries.yaml"
        self.dataset = base_dataset()
        self.settings = Settings(_env_file=None, vault_path=self.vault, data_path=self.data)

    def run(self, responder=None, capsys=None) -> tuple[int, dict | None, str]:
        self.dataset_path.write_text(yaml.safe_dump(self.dataset, allow_unicode=True))
        responder = responder or (lambda body: perfect(body, self.dataset))

        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=responder(json.loads(request.content)))

        code = ev.main(
            ["--dataset", str(self.dataset_path), "--base-url", "http://api"],
            settings=self.settings,
            transport=httpx.MockTransport(handle),
        )
        reports = sorted((self.data / "eval").glob("recall-*.json"))
        report = json.loads(reports[-1].read_text()) if reports else None
        err = capsys.readouterr().err if capsys else ""
        return code, report, err


@pytest.fixture
def harness(tmp_path) -> Harness:
    return Harness(tmp_path)


# --- metrics ------------------------------------------------------------------------


def test_metrics_are_computed_correctly():
    """Scenario: metrics are computed correctly."""
    assert ev.rank_of_expected(["co", "other", "exp"], "exp", ["co"]) == 2
    assert ev.rank_of_expected(["exp"], "exp", []) == 1
    assert ev.rank_of_expected(["a", "b"], "exp", []) is None
    ranks = [1, 2, None, 4]
    assert ev.recall_at_1(ranks) == 0.25
    assert ev.mean_reciprocal_rank(ranks) == pytest.approx((1 + 0.5 + 0 + 0.25) / 4)
    assert ev.p95([float(x) for x in range(1, 21)]) == 19.0

    dataset = ev.Dataset(
        queries=[
            ev.EvalQuery("q1", "prose", expected="Witt/a.md", allowed_cohits=["Witt/co.md"]),
            ev.EvalQuery("n1", "prose", must_not_appear=["x"]),
        ],
        gate_mrr=False,
        sha256="x",
    )
    responses = [
        {"hits": [_hit("Witt/co.md"), _hit("Witt/b.md"), _hit("Witt/a.md", 0.7)], "latency_ms": 5},
        {"hits": [_hit("Witt/b.md", 0.51), _hit("Witt/c.md", 0.47)], "latency_ms": 5},
    ]
    result = ev.evaluate(dataset, responses, vault_path=Path("/nope"), floor=0.4, corpus_notes=3)
    labelled, null = result["queries"]
    assert labelled["rank_of_expected"] == 2 and labelled["expected_similarity"] == 0.7
    assert (null["hits"], null["top_similarity"]) == (2, 0.51)
    assert result["metrics"]["recall_at_1"] == 0.0
    assert result["metrics"]["mrr"] == 0.5


def test_eval_constants_mirror_the_api():
    from secondbrain.api import recall

    assert (ev.K_LEX, ev.RRF_K) == (recall.K_LEX, recall.RRF_K)


# --- gates --------------------------------------------------------------------------


def _with(base: Responder, query: str, hits: list[dict]) -> Responder:
    def responder(body: dict) -> dict:
        out = base(body)
        if body["query"] == query:
            out = out | {"hits": hits}
        return out

    return responder


def _low_mrr(dataset: dict) -> Responder:
    """Half the labelled queries put the expected note at rank 5 (MRR 0.6)."""
    filler = [_hit(f"Witt/f{i}.md") for i in range(4)]

    def responder(body: dict) -> dict:
        out = perfect(body, dataset)
        q = next((q for q in dataset["queries"] if q["query"] == body["query"]), None)
        if q and q.get("expected") and dataset["queries"].index(q) % 2:
            out["hits"] = [*filler, _hit(q["expected"])]
        return out

    return responder


REPORT_KEYS = {
    "git_sha", "embedding_model", "hf_revision", "k_lex", "rrf_k", "recall_min_similarity",
    "context_generation_enabled", "witt_chunk_count", "witt_note_count", "dataset_sha256",
    "gates", "queries",
}  # fmt: skip


def _gate_case(name: str, h: Harness) -> tuple[Responder, str]:
    base = lambda body: perfect(body, h.dataset)  # noqa: E731
    prose = "may a spec skip its review if recorded"
    if name == "scope":
        return _with(base, prose, [_hit(ADR), _hit("10_Notes/cooking.md")]), "scope_isolation"
    if name == "rank6":
        others = [_hit(f"Witt/x{i}.md") for i in range(5)]
        return _with(base, prose, [*others, _hit(ADR)]), "expected_in_top5"
    if name == "cohit":
        return _with(base, "overrides", [_hit(HUB), _hit(COHIT)]), "expected_in_top5"
    if name == "margin":
        return _with(base, prose, [_hit(ADR, 0.44)]), "floor_margin"
    if name == "latency":
        return (lambda body: base(body) | {"latency_ms": 1200}), "latency"
    if name == "missing_label":
        h.dataset["queries"][5]["expected"] = "Witt/Projects/p/specs/999-gone.md"
        return base, "stale_labels"
    if name == "excluded_label":
        h.dataset["queries"][5]["expected"] = "Witt/Logs/2026-11-21.md"
        return base, "stale_labels"
    assert name == "mrr"
    h.dataset["gate_mrr"] = True
    return _low_mrr(h.dataset), "mrr"


@pytest.mark.parametrize(
    "case",
    ["scope", "rank6", "cohit", "margin", "latency", "missing_label", "excluded_label", "mrr"],
)
def test_failed_hard_gate_exits_non_zero_and_names_the_gate(harness, capsys, case):
    """Scenario: a failed hard gate exits non-zero and names the gate."""
    responder, gate = _gate_case(case, harness)
    code, report, err = harness.run(responder, capsys)

    assert code != 0
    assert gate in err
    assert gate in report["failed_gates"] and report["gates"][gate]["passed"] is False
    assert set(report) >= REPORT_KEYS


def test_all_gates_pass_on_a_clean_run(harness, capsys):
    code, report, err = harness.run(capsys=capsys)
    assert code == 0, err
    assert report["failed_gates"] == []
    assert report["witt_note_count"] == 5 and report["witt_chunk_count"] == 9


def test_mrr_gate_is_off_unless_the_dataset_turns_it_on(harness, capsys, tmp_path):
    """Scenario: the MRR gate is off unless the dataset turns it on."""
    # 16-note corpus, MRR 0.6, gate_mrr absent → exit 0 with the recommendation.
    write_vault(
        harness.vault, {f"Witt/Learnings/extra{i}.md": f"# E{i}\n\nextra {i}\n" for i in range(11)}
    )
    code, report, err = harness.run(_low_mrr(harness.dataset), capsys)
    assert report["witt_note_count"] == 16
    assert report["metrics"]["mrr"] == pytest.approx(0.6)
    assert code == 0 and "mrr" not in report["gates"]
    assert (
        "recommend gate_mrr: true" in err
        and "recommend gate_mrr: true" in report["recommendations"]
    )

    # 5-note corpus (7 in the scenario; any count ≤15), expected note at rank 4
    # → also recommended.
    small = Harness(tmp_path / "small")
    small.dataset = base_dataset()
    rank4 = _with(
        lambda b: perfect(b, small.dataset),
        "overrides",
        [_hit("Witt/f0.md"), _hit("Witt/f1.md"), _hit("Witt/f2.md"), _hit(ADR)],
    )
    code, report, err = small.run(rank4, capsys)
    assert report["witt_note_count"] <= 15
    assert code == 0 and "recommend gate_mrr: true" in err


# --- dataset validation ---------------------------------------------------------------


def _mutate(row: str, ds: dict) -> None:
    qs = ds["queries"]
    labelled = [q for q in qs if q.get("expected")]
    nulls = [q for q in qs if not q.get("expected")]
    if row == "7 labelled":
        qs.remove(labelled[-1])
    elif row == "3 null":
        qs.remove(nulls[-1])
    elif row == "1 identifier":
        labelled[1]["kind"] = "prose"
    elif row == "1 long":
        labelled[2]["kind"] = "prose"
    elif row == "no 1500":
        labelled[3]["query"] = "why we pin descriptions " + _words(120, "vl")  # long, <1500
    elif row == "no short":
        labelled[4]["kind"] = "identifier"
    elif row == "no exclude_paths":
        labelled[2]["filters"] = {}
    elif row == "1 near-miss":
        nulls[0]["near_miss"] = False
    elif row == "kind other":
        labelled[5]["kind"] = "other"
    elif row == "duplicate":
        qs.append(copy.deepcopy(labelled[5]))
    elif row == "verbatim prose":
        labelled[5]["query"] = "Overrides may skip review when they are recorded"
    else:
        assert row == "contaminated null"
        nulls[0]["must_not_appear"] = ["classify_witt_path"]


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("7 labelled", "too few labelled"),
        ("3 null", "too few null"),
        ("1 identifier", "too few identifier"),
        ("1 long", "too few long"),
        ("no 1500", "no query ≥1500 chars"),
        ("no short", "too few short"),
        ("no exclude_paths", "missing filter coverage: exclude_paths"),
        ("1 near-miss", "too few near-miss"),
        ("kind other", "bad kind"),
        ("duplicate", "duplicate query"),
        ("verbatim prose", "verbatim query"),
        ("contaminated null", "null contamination"),
    ],
)
def test_a_bad_dataset_is_refused(harness, capsys, row, reason):
    """Scenario: a bad dataset is refused."""
    _mutate(row, harness.dataset)
    code, report, err = harness.run(capsys=capsys)

    assert code == ev.EXIT_DATASET
    assert reason in err
    assert report is None


@pytest.mark.parametrize(
    "row",
    ["identifier verbatim", "short verbatim", "null term only in 10_Notes"],
)
def test_validation_exemptions_and_scoping(harness, row):
    """Scenario: validation exemptions and scoping."""
    qs = harness.dataset["queries"]
    if row == "identifier verbatim":
        assert "ADR-002" in NOTES[ADR]  # appears verbatim in its expected note
    elif row == "short verbatim":
        assert "overrides" in NOTES[ADR].lower()
    else:
        qs[-1]["must_not_appear"] = ["sourdough"]  # only in 10_Notes/cooking.md
    harness.dataset_path.write_text(yaml.safe_dump(harness.dataset))

    dataset = ev.load_dataset(harness.dataset_path)
    ev.validate_dataset(dataset, ev.witt_corpus(harness.vault))  # does not raise


def test_witt_corpus_is_indexed_witt_notes_only(harness):
    corpus = ev.witt_corpus(harness.vault)
    assert set(corpus) == {ADR, SPEC, HUB, LEARN, COHIT}


def test_eval_fails_loudly_when_the_api_is_down(tmp_path):
    """Scenario: eval fails loudly when the API is down."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ | {"SECONDBRAIN_PORT": str(port), "SECONDBRAIN_HOST": "127.0.0.1"}

    out = subprocess.run(
        [sys.executable, "-m", "secondbrain.eval.recall_eval"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert out.returncode != 0
    assert "unreachable" in out.stderr


def test_recall_queries_yaml_validates():
    """The committed dataset passes validation against this machine's Witt corpus."""
    settings = Settings()
    if settings.vault_path is None or not (Path(settings.vault_path) / "Witt").is_dir():
        pytest.skip("Witt vault not present on this machine")
    dataset = ev.load_dataset(ev.DEFAULT_DATASET)
    ev.validate_dataset(dataset, ev.witt_corpus(Path(settings.vault_path)))
    for q in dataset.labelled:
        assert q.expected is not None
        assert (Path(settings.vault_path) / q.expected).is_file(), q.expected
