"""Tests for the push digest reducer (compact projection of the briefing)."""

from secondbrain.api.briefing import _build_digest, _short_date
from secondbrain.models import BriefingResponse, BriefingTask


def _task(text: str = "Do the thing") -> BriefingTask:
    return BriefingTask(
        text=text,
        category="Personal",
        sub_project="",
        due_date="",
        days_open=1,
        first_date="2026-08-01",
    )


def _briefing(
    *,
    overdue: int = 0,
    due: int = 0,
    aging: int = 0,
    today: str = "2026-08-02",
) -> BriefingResponse:
    return BriefingResponse(
        today=today,
        today_display="Saturday, August 2, 2026",
        overdue_tasks=[_task() for _ in range(overdue)],
        due_today_tasks=[_task() for _ in range(due)],
        aging_followups=[_task() for _ in range(aging)],
        yesterday_context=None,
        today_context=None,
        today_events=[],
        total_open=overdue + due + aging,
    )


class TestShortDate:
    def test_formats_iso_date(self):
        assert _short_date("2026-08-02") == "Aug 2"

    def test_double_digit_day(self):
        assert _short_date("2026-12-25") == "Dec 25"

    def test_invalid_input_passes_through(self):
        assert _short_date("not-a-date") == "not-a-date"


class TestBuildDigest:
    def test_all_clear_is_quiet(self):
        d = _build_digest(_briefing())
        assert d.count == 0
        assert d.body == "All clear — nothing needs attention."
        assert d.title == "SecondBrain · Aug 2"

    def test_only_overdue(self):
        d = _build_digest(_briefing(overdue=3))
        assert d.count == 3
        assert d.body == "3 overdue"

    def test_only_due_today(self):
        d = _build_digest(_briefing(due=2))
        assert d.count == 2
        assert d.body == "2 due today"

    def test_single_aging_is_singular(self):
        d = _build_digest(_briefing(aging=1))
        assert d.body == "1 aging follow-up"

    def test_multiple_aging_is_plural(self):
        d = _build_digest(_briefing(aging=4))
        assert d.body == "4 aging follow-ups"

    def test_mixed_joins_in_order(self):
        d = _build_digest(_briefing(overdue=3, due=2, aging=1))
        assert d.count == 6
        assert d.body == "3 overdue · 2 due today · 1 aging follow-up"

    def test_skips_zero_segments(self):
        d = _build_digest(_briefing(overdue=1, aging=2))
        assert d.body == "1 overdue · 2 aging follow-ups"

    def test_title_reflects_date(self):
        d = _build_digest(_briefing(overdue=1, today="2026-01-09"))
        assert d.title == "SecondBrain · Jan 9"
