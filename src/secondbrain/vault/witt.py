"""Witt's vault layout: where Witt writes notes, and what kind each path is (spec 001).

Witt writes specs, decisions, learnings and project hubs under ``Witt/`` in the vault.
Kind and project are derived from the path, so a Witt layout change is contained here.
"""

from secondbrain.models import RecallKind

WITT_FOLDER = "Witt"
# Witt's daily logs: rewritten all day, breadcrumbs rather than notes. fnmatch `*` crosses `/`,
# so Witt/Logs/archive/x.md is excluded too.
WITT_LOG_EXCLUDE = "Witt/Logs/*"

_PROJECT_SUBDIR_KINDS: dict[str, RecallKind] = {"specs": "spec", "decisions": "decision"}


def is_witt_path(note_path: str) -> bool:
    """True when a vault-relative path lives under the Witt folder (first segment only).

    ``10_Notes/Witt/x.md`` and ``Wittgenstein/x.md`` are ordinary notes.
    """
    return note_path.split("/", 1)[0] == WITT_FOLDER


def classify_witt_path(note_path: str) -> tuple[RecallKind, str | None]:
    """Map a vault-relative path to (kind, project slug). Pure; never raises.

    | Path                                      | Kind     |
    |-------------------------------------------|----------|
    | Witt/Projects/{slug}/specs/**.md          | spec     |
    | Witt/Projects/{slug}/decisions/**.md      | decision |
    | Witt/Projects/{slug}/{slug}.md            | project  |
    | Witt/Learnings/**.md                      | learning |
    | anything else                             | other    |

    The project is set only for spec, decision and project kinds. Empty, degenerate or
    non-Witt paths return ("other", None).
    """
    parts = note_path.split("/")
    if len(parts) < 3 or parts[0] != WITT_FOLDER or not all(parts):
        return "other", None
    if parts[1] == "Learnings":
        return "learning", None
    if parts[1] != "Projects" or len(parts) < 4:
        return "other", None
    slug = parts[2]
    if len(parts) >= 5 and parts[3] in _PROJECT_SUBDIR_KINDS:
        return _PROJECT_SUBDIR_KINDS[parts[3]], slug
    if len(parts) == 4 and parts[3] == f"{slug}.md":
        return "project", slug
    return "other", None
