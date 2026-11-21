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


def copy_index(src: RecallIndex, dest: Path) -> RecallIndex:
    """Copy an index's data directory so a test can write to its own stores."""
    shutil.copytree(src.data_path, dest)
    return open_index(src.vault_path, dest, make_stub_embedder())


def note(title: str, sim: float, body: str) -> str:
    """Fixture note: an H1, a sim marker and a body (pad to the chunker's 100-char minimum)."""
    text = body if len(body) >= 100 else body + " " + "filler text " * 10
    return f"# {title}\n\n<!-- sim:{sim:.2f} -->\n{text}\n"
