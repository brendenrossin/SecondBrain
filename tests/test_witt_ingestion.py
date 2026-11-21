"""Spec 001 — Feature: Witt ingestion policy."""

import logging
from pathlib import Path
from unittest.mock import patch

from secondbrain.indexing.chunker import Chunker
from secondbrain.vault.connector import VaultConnector
from secondbrain.vault.parser import parse_markdown
from secondbrain.vault.witt import WITT_LOG_EXCLUDE
from tests.fixtures.recall.index import build_index, note, reindex, write_vault

LOG = "Witt/Logs/2026-11-21.md"
ADR = "Witt/Projects/witt/decisions/ADR-001-overrides.md"
SPEC = "Witt/Projects/witt/specs/001-harness.md"
LEARNING = "Witt/Learnings/pin-the-docstring.md"


def _witt_vault(root: Path) -> Path:
    return write_vault(
        root,
        {
            LOG: note("2026-11-21", 0.6, "Log entry about building the review process today."),
            ADR: note("Overrides", 0.7, "Overrides may skip review when they are recorded."),
            SPEC: note("Harness", 0.8, "The harness gates status changes through review."),
            LEARNING: note("Pin it", 0.5, "Pin the tool description in the spec."),
        },
    )


def _chunk_counts(idx, path: str) -> tuple[int, int, int | None]:
    lex = idx.lexical_store.conn.execute(
        "SELECT count(*) FROM chunks WHERE note_path = ?", (path,)
    ).fetchone()[0]
    vec = len(idx.vector_store.collection.get(where={"note_path": path}, include=[])["ids"])
    row = idx.tracker.conn.execute(
        "SELECT chunk_count FROM indexed_files WHERE file_path = ?", (path,)
    ).fetchone()
    return lex, vec, (row[0] if row else None)


def test_witt_daily_logs_excluded_other_witt_notes_listed(tmp_path):
    """Scenario: Witt daily logs are excluded, other Witt notes are listed."""
    vault = _witt_vault(tmp_path / "vault")
    write_vault(
        vault,
        {
            "Witt/Logs/archive/old.md": "# Old\n\nold log\n",
            "10_Notes/Witt/Logs/x.md": "# X\n\nnot a Witt log\n",
        },
    )

    listed = {str(p) for p in VaultConnector(vault).list_notes()}

    assert LOG not in listed
    assert "Witt/Logs/archive/old.md" not in listed
    assert {"10_Notes/Witt/Logs/x.md", ADR, SPEC, LEARNING} <= listed


def test_previously_indexed_logs_removed_by_production_reindex(tmp_path):
    """Scenario: previously indexed logs are removed by the production reindex, and nothing else is."""
    vault = _witt_vault(tmp_path / "vault")
    old_excludes = [p for p in VaultConnector.DEFAULT_EXCLUDES if p != WITT_LOG_EXCLUDE]
    with patch.object(VaultConnector, "DEFAULT_EXCLUDES", old_excludes):
        idx = build_index(vault, tmp_path / "data")
    assert _chunk_counts(idx, LOG)[0] > 0  # the log really was indexed before the exclusion
    before = {p: _chunk_counts(idx, p) for p in (ADR, SPEC, LEARNING)}

    reindex(idx)  # _run_indexing, as POST /api/v1/index does

    assert _chunk_counts(idx, LOG) == (0, 0, None)
    assert {p: _chunk_counts(idx, p) for p in (ADR, SPEC, LEARNING)} == before
    assert all(lex > 0 and lex == vec == tracked for lex, vec, tracked in before.values())


def test_witt_frontmatter_stripped_and_titles_resolve():
    """Scenario: Witt frontmatter is stripped and titles resolve."""
    body = "\n\nThe harness gates every status change and records overrides in history. " * 3
    spec = (
        "---\ntitle: Witt v0 harness MVP\ntype: spec\nsource: witt\nproject: witt\n---\n# H" + body
    )
    adr = "---\ntype: decision\n---\n# Overrides may skip Review when recorded" + body
    numbered = "---\ntitle: 2026\n---\n# Numbers" + body
    chunker = Chunker()

    notes = [
        parse_markdown("Witt/Projects/witt/specs/001.md", spec),
        parse_markdown("Witt/Projects/witt/decisions/ADR-001.md", adr),
        parse_markdown("Witt/Learnings/n.md", numbered),
    ]
    chunks = [c for n in notes for c in chunker.chunk_note(n)]

    assert chunks
    assert not any("type:" in c.chunk_text or "source: witt" in c.chunk_text for c in chunks)
    assert [n.title for n in notes] == [
        "Witt v0 harness MVP",
        "Overrides may skip Review when recorded",
        "Numbers",
    ]


def test_malformed_frontmatter_skips_the_note_not_the_reindex(tmp_path, caplog):
    """Scenario: malformed frontmatter skips the note, not the reindex."""
    bad = "Witt/Projects/witt/specs/bad.md"
    vault = _witt_vault(tmp_path / "vault")
    write_vault(vault, {bad: "---\ntitle: [unclosed\n  : : bad\n---\n# Bad\n\nbody text\n"})

    with caplog.at_level(logging.WARNING):
        idx = build_index(vault, tmp_path / "data")

    assert any(bad in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    for path in (ADR, SPEC, LEARNING):
        assert _chunk_counts(idx, path)[0] > 0
    assert _chunk_counts(idx, bad)[2] is None
