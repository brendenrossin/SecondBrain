"""Event parser: scans daily notes for ## Events sections and extracts calendar events."""

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

# Patterns for parsing event bullets
# Timed event: "- 10:30 — Event title" or "- 10:30 - Event title"
TIMED_RE = re.compile(r"^-\s*(\d{1,2}:\d{2})\s*[—–-]\s*(.+)$")
# Multi-day end: "(through YYYY-MM-DD)" at end of line
MULTI_DAY_RE = re.compile(r"\(through\s+(\d{4}-\d{2}-\d{2})\)\s*$")


@dataclass
class Event:
    """A calendar event extracted from a daily note."""

    title: str
    date: str  # YYYY-MM-DD
    time: str  # "HH:MM" or ""
    end_date: str  # "YYYY-MM-DD" or ""
    source_file: str


def scan_daily_notes_for_events(daily_dir: Path) -> list[Event]:
    """Scan all daily notes for ## Events sections.

    Returns all events found, sorted by date then time.
    """
    if not daily_dir.exists():
        return []

    events: list[Event] = []
    for md_file in sorted(daily_dir.glob("*.md")):
        date_str = md_file.stem
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            continue
        events.extend(_parse_events_from_file(md_file, date_str))

    events.sort(key=lambda e: (e.date, e.time))
    return events


def _parse_events_from_file(md_file: Path, date_str: str) -> list[Event]:
    """Parse events from a daily note's ## Events section."""
    lines = md_file.read_text(encoding="utf-8").split("\n")
    events: list[Event] = []
    in_events_section = False

    for line in lines:
        stripped = line.strip()

        if stripped == "## Events":
            in_events_section = True
            continue

        if in_events_section and stripped.startswith("## "):
            break

        if not in_events_section:
            continue

        if not stripped.startswith("- "):
            continue

        # Try timed event first
        timed_match = TIMED_RE.match(stripped)
        if timed_match:
            time_str = timed_match.group(1)
            title = timed_match.group(2).strip()
        else:
            time_str = ""
            title = stripped[2:].strip()

        if not title:
            continue

        # Check for multi-day end date
        end_date = ""
        multi_match = MULTI_DAY_RE.search(title)
        if multi_match:
            end_date = multi_match.group(1)
            title = MULTI_DAY_RE.sub("", title).strip()

        events.append(
            Event(
                title=title,
                date=date_str,
                time=time_str,
                end_date=end_date,
                source_file=str(md_file),
            )
        )

    return events


def get_events_in_range(daily_dir: Path, start: date, end: date) -> list[Event]:
    """Get all events that overlap with the given date range.

    Multi-day events are included if any part of their span overlaps the range.
    """
    all_events = scan_daily_notes_for_events(daily_dir)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    result: list[Event] = []
    for event in all_events:
        event_start = event.date
        event_end = event.end_date or event.date

        # Check overlap: event range [event_start, event_end] with query [start_str, end_str]
        if event_end >= start_str and event_start <= end_str:
            result.append(event)

    return result
