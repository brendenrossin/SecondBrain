"""Tests for the event parser."""

from datetime import date
from pathlib import Path

from secondbrain.scripts.event_parser import (
    _parse_events_from_file,
    get_events_in_range,
    scan_daily_notes_for_events,
)


def _make_daily_note(daily_dir: Path, date_str: str, content: str) -> None:
    """Write a daily note file."""
    daily_dir.mkdir(parents=True, exist_ok=True)
    (daily_dir / f"{date_str}.md").write_text(content, encoding="utf-8")


DAILY_WITH_EVENTS = """\
---
type: daily
date: {date}
---

## Events
{events}

## Focus
- Work

## Tasks
### Personal
- [ ] Something
"""


class TestParseEvents:
    def test_timed_event(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-10",
            DAILY_WITH_EVENTS.format(date="2026-02-10", events="- 10:30 — Mom visiting"),
        )
        events = _parse_events_from_file(daily_dir / "2026-02-10.md", "2026-02-10")
        assert len(events) == 1
        assert events[0].title == "Mom visiting"
        assert events[0].time == "10:30"
        assert events[0].date == "2026-02-10"

    def test_timed_event_dash(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-10",
            DAILY_WITH_EVENTS.format(date="2026-02-10", events="- 14:00 - Dentist appointment"),
        )
        events = _parse_events_from_file(daily_dir / "2026-02-10.md", "2026-02-10")
        assert len(events) == 1
        assert events[0].title == "Dentist appointment"
        assert events[0].time == "14:00"

    def test_all_day_event(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-10",
            DAILY_WITH_EVENTS.format(date="2026-02-10", events="- Company offsite"),
        )
        events = _parse_events_from_file(daily_dir / "2026-02-10.md", "2026-02-10")
        assert len(events) == 1
        assert events[0].title == "Company offsite"
        assert events[0].time == ""

    def test_multi_day_event(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-20",
            DAILY_WITH_EVENTS.format(
                date="2026-02-20", events="- Vacation (through 2026-02-24)"
            ),
        )
        events = _parse_events_from_file(daily_dir / "2026-02-20.md", "2026-02-20")
        assert len(events) == 1
        assert events[0].title == "Vacation"
        assert events[0].end_date == "2026-02-24"

    def test_multiple_events(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-10",
            DAILY_WITH_EVENTS.format(
                date="2026-02-10",
                events="- 9:00 — Standup\n- 14:00 — Dentist\n- Team dinner",
            ),
        )
        events = _parse_events_from_file(daily_dir / "2026-02-10.md", "2026-02-10")
        assert len(events) == 3
        assert events[0].time == "9:00"
        assert events[1].time == "14:00"
        assert events[2].time == ""

    def test_no_events_section(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        content = "---\ntype: daily\n---\n\n## Focus\n- Work\n\n## Tasks\n- [ ] Task"
        _make_daily_note(daily_dir, "2026-02-10", content)
        events = _parse_events_from_file(daily_dir / "2026-02-10.md", "2026-02-10")
        assert events == []

    def test_empty_events_section(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-10",
            DAILY_WITH_EVENTS.format(date="2026-02-10", events=""),
        )
        events = _parse_events_from_file(daily_dir / "2026-02-10.md", "2026-02-10")
        assert events == []


class TestScanDailyNotes:
    def test_scans_multiple_days(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-10",
            DAILY_WITH_EVENTS.format(date="2026-02-10", events="- 10:00 — Meeting"),
        )
        _make_daily_note(
            daily_dir,
            "2026-02-11",
            DAILY_WITH_EVENTS.format(date="2026-02-11", events="- Lunch with Sarah"),
        )

        events = scan_daily_notes_for_events(daily_dir)
        assert len(events) == 2
        assert events[0].date == "2026-02-10"
        assert events[1].date == "2026-02-11"

    def test_empty_dir(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        events = scan_daily_notes_for_events(daily_dir)
        assert events == []

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        events = scan_daily_notes_for_events(tmp_path / "nonexistent")
        assert events == []


class TestGetEventsInRange:
    def test_single_day_in_range(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-10",
            DAILY_WITH_EVENTS.format(date="2026-02-10", events="- Meeting"),
        )
        _make_daily_note(
            daily_dir,
            "2026-02-20",
            DAILY_WITH_EVENTS.format(date="2026-02-20", events="- Other meeting"),
        )

        events = get_events_in_range(daily_dir, date(2026, 2, 9), date(2026, 2, 15))
        assert len(events) == 1
        assert events[0].title == "Meeting"

    def test_multi_day_overlap(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-08",
            DAILY_WITH_EVENTS.format(
                date="2026-02-08", events="- Vacation (through 2026-02-14)"
            ),
        )

        # Query range starts during the vacation
        events = get_events_in_range(daily_dir, date(2026, 2, 10), date(2026, 2, 16))
        assert len(events) == 1
        assert events[0].title == "Vacation"

    def test_multi_day_ends_on_range_start(self, tmp_path: Path) -> None:
        """Event ending exactly on the query range start should be included."""
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-08",
            DAILY_WITH_EVENTS.format(
                date="2026-02-08", events="- Conference (through 2026-02-10)"
            ),
        )

        events = get_events_in_range(daily_dir, date(2026, 2, 10), date(2026, 2, 16))
        assert len(events) == 1
        assert events[0].title == "Conference"

    def test_multi_day_starts_on_range_end(self, tmp_path: Path) -> None:
        """Event starting exactly on the query range end should be included."""
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-16",
            DAILY_WITH_EVENTS.format(
                date="2026-02-16", events="- Workshop (through 2026-02-18)"
            ),
        )

        events = get_events_in_range(daily_dir, date(2026, 2, 10), date(2026, 2, 16))
        assert len(events) == 1
        assert events[0].title == "Workshop"

    def test_multi_day_no_overlap(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-01",
            DAILY_WITH_EVENTS.format(
                date="2026-02-01", events="- Trip (through 2026-02-05)"
            ),
        )

        events = get_events_in_range(daily_dir, date(2026, 2, 10), date(2026, 2, 16))
        assert len(events) == 0

    def test_empty_range(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir(parents=True, exist_ok=True)

        events = get_events_in_range(daily_dir, date(2026, 2, 10), date(2026, 2, 16))
        assert events == []
