"""Tests for the weekly review generator."""

from datetime import date
from pathlib import Path

from secondbrain.scripts.weekly_review import (
    _collect_week_data,
    _extract_words,
    _get_week_boundaries,
    _render_weekly_note,
    generate_weekly_review,
)


def _make_daily_note(daily_dir: Path, date_str: str, content: str) -> None:
    """Write a daily note file."""
    daily_dir.mkdir(parents=True, exist_ok=True)
    (daily_dir / f"{date_str}.md").write_text(content, encoding="utf-8")


DAILY_TEMPLATE = """\
---
type: daily
date: {date}
tags: []
---

## Focus
{focus}

## Notes
{notes}

## Tasks
### {category}
{tasks}
"""


class TestWeekBoundaries:
    def test_mid_week_date(self) -> None:
        # Wednesday 2026-02-04
        start, end, key = _get_week_boundaries(date(2026, 2, 4))
        assert start == date(2026, 2, 2)  # Monday
        assert end == date(2026, 2, 8)  # Sunday
        assert key == "2026-W06"

    def test_monday(self) -> None:
        start, end, key = _get_week_boundaries(date(2026, 2, 2))
        assert start == date(2026, 2, 2)
        assert end == date(2026, 2, 8)

    def test_sunday(self) -> None:
        start, end, key = _get_week_boundaries(date(2026, 2, 8))
        assert start == date(2026, 2, 2)
        assert end == date(2026, 2, 8)

    def test_year_boundary(self) -> None:
        # Dec 29, 2025 is a Monday in ISO week 1 of 2026
        start, end, key = _get_week_boundaries(date(2025, 12, 31))
        assert start == date(2025, 12, 29)
        assert end == date(2026, 1, 4)
        assert key == "2026-W01"

    def test_early_january(self) -> None:
        # Jan 1, 2026 is in ISO week 1 of 2026
        start, end, key = _get_week_boundaries(date(2026, 1, 1))
        assert start == date(2025, 12, 29)
        assert end == date(2026, 1, 4)
        assert key == "2026-W01"


class TestExtractWords:
    def test_basic(self) -> None:
        words = _extract_words("Azure certification prep")
        assert "azure" in words
        assert "certification" in words
        assert "prep" in words

    def test_stopwords_removed(self) -> None:
        words = _extract_words("the quick brown fox and the lazy dog")
        assert "the" not in words
        assert "and" not in words
        assert "quick" in words

    def test_short_words_removed(self) -> None:
        words = _extract_words("AI is on the go")
        assert "ai" not in words  # len < 3
        assert "is" not in words


class TestCollectWeekData:
    def test_focus_items_collected(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-02",
            DAILY_TEMPLATE.format(
                date="2026-02-02",
                focus="- Azure certification prep",
                notes="- Called Sarah",
                category="Personal",
                tasks="- [ ] Study for exam",
            ),
        )
        _make_daily_note(
            daily_dir,
            "2026-02-04",
            DAILY_TEMPLATE.format(
                date="2026-02-04",
                focus="- Azure certification prep\n- Q2 planning",
                notes="- Team standup went well",
                category="Personal",
                tasks="- [x] Study for exam",
            ),
        )

        data = _collect_week_data(daily_dir, date(2026, 2, 2), date(2026, 2, 8), "2026-W06")
        focus_texts = [item for item, _ in data.focus_items]
        assert "Azure certification prep" in focus_texts
        assert "Q2 planning" in focus_texts

        # Azure cert appeared Mon + Wed
        for item, days in data.focus_items:
            if item == "Azure certification prep":
                assert "Mon" in days
                assert "Wed" in days

    def test_tasks_aggregated(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-02",
            DAILY_TEMPLATE.format(
                date="2026-02-02",
                focus="- Work",
                notes="- Note",
                category="Personal",
                tasks="- [x] File taxes\n- [ ] Review SOC 2 report (due: 2026-02-12)",
            ),
        )

        data = _collect_week_data(daily_dir, date(2026, 2, 2), date(2026, 2, 8), "2026-W06")
        assert len(data.completed_tasks) == 1
        assert data.completed_tasks[0].text == "File taxes"
        assert len(data.open_tasks) == 1
        assert data.open_tasks[0].text == "Review SOC 2 report"

    def test_notes_collected(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-03",
            DAILY_TEMPLATE.format(
                date="2026-02-03",
                focus="- Focus",
                notes="- Rachel is visiting next week\n- Tried miso black cod",
                category="Personal",
                tasks="- [ ] Something",
            ),
        )

        data = _collect_week_data(daily_dir, date(2026, 2, 2), date(2026, 2, 8), "2026-W06")
        note_texts = [item for item, _ in data.notes_items]
        assert "Rachel is visiting next week" in note_texts
        assert "Tried miso black cod" in note_texts

    def test_recurring_topics(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        # "azure" and "certification" appear across 3 days
        for _day_offset, date_str in [(0, "2026-02-02"), (2, "2026-02-04"), (4, "2026-02-06")]:
            _make_daily_note(
                daily_dir,
                date_str,
                DAILY_TEMPLATE.format(
                    date=date_str,
                    focus="- Azure certification work",
                    notes="- Some note",
                    category="Personal",
                    tasks="- [ ] Task",
                ),
            )

        data = _collect_week_data(daily_dir, date(2026, 2, 2), date(2026, 2, 8), "2026-W06")
        assert "azure" in data.recurring_topics
        assert "certification" in data.recurring_topics

    def test_empty_week(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir(parents=True, exist_ok=True)

        data = _collect_week_data(daily_dir, date(2026, 2, 2), date(2026, 2, 8), "2026-W06")
        assert data.focus_items == []
        assert data.completed_tasks == []
        assert data.open_tasks == []
        assert data.notes_items == []
        assert data.recurring_topics == []


class TestRenderWeeklyNote:
    def test_frontmatter(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        data = _collect_week_data(daily_dir, date(2026, 2, 2), date(2026, 2, 8), "2026-W06")
        content = _render_weekly_note(data)

        assert "type: weekly" in content
        assert "week: 2026-W06" in content
        assert "start_date: 2026-02-02" in content
        assert "end_date: 2026-02-08" in content
        assert "# Week 6" in content

    def test_sections_present(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-02",
            DAILY_TEMPLATE.format(
                date="2026-02-02",
                focus="- Azure prep",
                notes="- Good day",
                category="Personal",
                tasks="- [x] Done task\n- [ ] Open task",
            ),
        )

        data = _collect_week_data(daily_dir, date(2026, 2, 2), date(2026, 2, 8), "2026-W06")
        content = _render_weekly_note(data)

        assert "## Focus Areas" in content
        assert "- Azure prep (Mon)" in content
        assert "## Completed" in content
        assert "- Done task" in content
        assert "## Still Open" in content
        assert "- [ ] Open task" in content
        assert "## Notes & Observations" in content
        assert "- Good day" in content
        assert "## Recurring Topics" in content


class TestGenerateWeeklyReview:
    def test_creates_file(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-02",
            DAILY_TEMPLATE.format(
                date="2026-02-02",
                focus="- Focus",
                notes="- Note",
                category="Personal",
                tasks="- [ ] Task",
            ),
        )

        result = generate_weekly_review(tmp_path, target_date=date(2026, 2, 4))
        assert "2026-W06" in result

        output = tmp_path / "00_Weekly" / "2026-W06.md"
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "type: weekly" in content

    def test_idempotent(self, tmp_path: Path) -> None:
        daily_dir = tmp_path / "00_Daily"
        _make_daily_note(
            daily_dir,
            "2026-02-02",
            DAILY_TEMPLATE.format(
                date="2026-02-02",
                focus="- Focus",
                notes="- Note",
                category="Personal",
                tasks="- [ ] Task",
            ),
        )

        generate_weekly_review(tmp_path, target_date=date(2026, 2, 4))
        generate_weekly_review(tmp_path, target_date=date(2026, 2, 4))

        # Only one file should exist
        output = tmp_path / "00_Weekly" / "2026-W06.md"
        assert output.exists()
        content = output.read_text(encoding="utf-8")
        # Should not have duplicate content
        assert content.count("## Focus Areas") == 1
