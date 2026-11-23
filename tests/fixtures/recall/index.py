"""Build real stores over fixture markdown (spec 001 fixture kit).

The index is built through the production path (`_run_indexing`: real VaultConnector,
Chunker, VectorStore, LexicalStore and IndexTracker) into a temp directory, never
into the repo.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from secondbrain.api.index import _run_indexing
from secondbrain.indexing.embedder import Embedder
from secondbrain.stores.index_tracker import IndexTracker
from secondbrain.stores.lexical import LexicalStore
from secondbrain.stores.vector import VectorStore
from tests.fixtures.recall.stub_embedder import make_stub_embedder

FIXTURE_VAULT = Path(__file__).parent / "vault"
GOLDENS_PATH = Path(__file__).parent / "goldens.json"
TEST_QUERY = "override review process"

# Spec 004: a separate vault where some Witt notes match only lexically (sim < 0.40 floor).
LEXONLY_QUERY = "quokka"
LEXONLY_VECTOR_NOTES = {
    "Witt/Projects/witt/decisions/ADR-010-lex.md": 0.70,  # also matches LEXONLY_QUERY
    "Witt/Projects/witt/specs/010-lex.md": 0.60,
    "Witt/Projects/second-brain/specs/020-lex.md": 0.50,
    "Witt/Learnings/lex-learning.md": 0.40,
}
LEXONLY_KEYWORD_NOTES = {
    "Witt/Projects/witt/decisions/ADR-011-kw.md": 0.10,
    "Witt/Projects/second-brain/specs/021-kw.md": 0.20,
    "Witt/Learnings/kw-learning.md": 0.30,
}
_LEXONLY_MATCHES = {"Witt/Projects/witt/decisions/ADR-010-lex.md", *LEXONLY_KEYWORD_NOTES}


@dataclass
class RecallIndex:
    vault_path: Path
    data_path: Path
    vector_store: VectorStore
    lexical_store: LexicalStore
    tracker: IndexTracker
    embedder: Embedder


def open_index(vault_path: Path, data_path: Path, embedder: Embedder | None = None) -> RecallIndex:
    """Open (creating if needed) stores under data_path, without indexing."""
    return RecallIndex(
        vault_path=vault_path,
        data_path=data_path,
        vector_store=VectorStore(data_path / "chroma"),
        lexical_store=LexicalStore(data_path / "lexical.db"),
        tracker=IndexTracker(data_path / "index_tracker.db"),
        embedder=embedder or make_stub_embedder(),
    )


def build_index(vault_path: Path, data_path: Path, embedder: Embedder | None = None) -> RecallIndex:
    """Index vault_path into fresh stores under data_path with the stub embedder."""
    idx = open_index(vault_path, data_path, embedder)
    reindex(idx)
    return idx


def reindex(idx: RecallIndex) -> None:
    """Run the production incremental indexer over idx.vault_path."""
    _run_indexing(
        idx.vault_path,
        idx.vector_store,
        idx.lexical_store,
        idx.embedder,
        idx.tracker,
        full_rebuild=False,
    )


def write_vault(root: Path, notes: dict[str, str]) -> Path:
    """Write {vault-relative path: markdown} under root and return root."""
    for rel, content in notes.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def build_lexonly_index(root: Path) -> RecallIndex:
    """Write the LEXONLY vault under root/vault and index it into root/data.

    7 Witt chunks: 4 at sim >= 0.40 (one also matching LEXONLY_QUERY lexically) and
    3 at sim < 0.40 that match LEXONLY_QUERY lexically. FIXTURE_VAULT is not involved.
    """
    notes = {}
    for i, (rel, sim) in enumerate((LEXONLY_VECTOR_NOTES | LEXONLY_KEYWORD_NOTES).items()):
        body = f"lexonly note {i} plain words"
        if rel in _LEXONLY_MATCHES:
            body = f"{LEXONLY_QUERY} {body}"
        notes[rel] = note(f"Lexonly {i}", sim, body)
    return build_index(write_vault(root / "vault", notes), root / "data")


def copy_index(src: RecallIndex, dest: Path) -> RecallIndex:
    """Copy an index's data directory so a test can write to its own stores."""
    shutil.copytree(src.data_path, dest)
    return open_index(src.vault_path, dest, make_stub_embedder())


def note(title: str, sim: float, body: str) -> str:
    """Fixture note: an H1, a sim marker and a body (pad to the chunker's 100-char minimum)."""
    text = body if len(body) >= 100 else body + " " + "filler text " * 10
    return f"# {title}\n\n<!-- sim:{sim:.2f} -->\n{text}\n"
