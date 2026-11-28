"""Spec 001 — Feature: path classification."""

import pytest

from secondbrain.vault.witt import WITT_FOLDER, WITT_LOG_EXCLUDE, classify_witt_path, is_witt_path


@pytest.mark.parametrize(
    ("path", "kind", "project"),
    [
        ("Witt/Projects/witt/specs/001-witt-v0-harness-mvp.md", "spec", "witt"),
        ("Witt/Projects/witt/specs/sub/x.md", "spec", "witt"),
        ("Witt/Projects/witt/decisions/ADR-001-x.md", "decision", "witt"),
        ("Witt/Projects/second-brain/second-brain.md", "project", "second-brain"),
        ("Witt/Projects/a/b.md", "other", None),
        ("Witt/Projects/witt/other.md", "other", None),
        ("Witt/README.md", "other", None),
        ("Witt/Learnings/some-lesson.md", "learning", None),
        ("Witt/Learnings/sub/x.md", "learning", None),
        ("10_Notes/recipes.md", "other", None),
    ],
)
def test_witt_paths_map_to_kind_and_project(path, kind, project):
    """Scenario: Witt paths map to kind and project."""
    assert classify_witt_path(path) == (kind, project)


@pytest.mark.parametrize("path", ["", "Witt", "Witt/", "Witt/Projects/"])
def test_degenerate_paths_never_raise(path):
    """Scenario: degenerate paths never raise."""
    assert classify_witt_path(path) == ("other", None)


def test_layout_constants():
    assert WITT_FOLDER == "Witt"
    assert WITT_LOG_EXCLUDE == "Witt/Logs/*"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("Witt/Learnings/n.md", True),
        ("Witt/Projects/witt/decisions/ADR-1.md", True),
        ("10_Notes/Witt/notes.md", False),
        ("Wittgenstein/Tractatus.md", False),
        ("10_Notes/Test.md", False),
        ("", False),
    ],
)
def test_is_witt_path(path, expected):
    """Spec 008: only paths whose first segment is the Witt folder are Witt notes."""
    assert is_witt_path(path) is expected
