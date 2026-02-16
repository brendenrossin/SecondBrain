"""User-configurable settings stored in data/settings.json."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: dict[str, Any] = {
    "categories": [
        {
            "name": "Work",
            "sub_projects": {},
        },
        {
            "name": "Personal",
            "sub_projects": {
                "Family": "family logistics, visits, coordination with family members",
                "Rachel": "anything specific to Rachel — relationship, proposal, dates, gifts for Rachel",
                "Gifts": "gifts for anyone (birthdays, holidays, occasions)",
                "Health": "medical appointments, fitness, wellness",
                "Errands": "one-off errands, pickups, drop-offs",
                "Chores": "recurring household tasks (cleaning, laundry, etc.)",
                "Projects": "personal projects with ongoing scope",
                "General": "anything that doesn't clearly fit above",
            },
        },
    ]
}

_SETTINGS_FILE = "settings.json"


def load_settings(data_path: Path) -> dict[str, Any]:
    """Read settings from data_path/settings.json.

    Returns DEFAULT_SETTINGS and writes the defaults file if missing or unparseable.
    """
    settings_file = data_path / _SETTINGS_FILE
    if settings_file.exists():
        try:
            with open(settings_file, encoding="utf-8") as f:
                result: dict[str, Any] = json.load(f)
                return result
        except (json.JSONDecodeError, OSError):
            logger.warning("Settings file corrupt or unreadable, returning defaults")
    # Write defaults so the file exists for next time
    save_settings(data_path, DEFAULT_SETTINGS)
    return DEFAULT_SETTINGS.copy()


def save_settings(data_path: Path, settings: dict[str, Any]) -> None:
    """Write settings to data_path/settings.json using atomic write."""
    data_path.mkdir(parents=True, exist_ok=True)
    settings_file = data_path / _SETTINGS_FILE
    fd, tmp_path = tempfile.mkstemp(dir=str(data_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, str(settings_file))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
