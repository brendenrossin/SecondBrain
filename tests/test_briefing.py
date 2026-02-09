"""Tests for the morning briefing: daily note section parsing and lookback."""

from datetime import datetime, timedelta

from secondbrain.scripts.task_aggregator import (
    find_recent_daily_context,
    parse_daily_note_sections,
)


class TestParseDailyNoteSections:
    def test_parses_focus_and_notes(self, tmp_path):
        md = tmp_path / "2026-02-07.md"
        md.write_text(
            "## Focus\n"
            "- Super Bowl party\n"
            "- Finish project\n"
            "\n"
            "## Notes\n"
            "- Rachel is my girlfriend\n"
            "- Try Trader Joe's miso black cod\n"
            "\n"
            "## Tasks\n"
            "### Personal\n"
            "- [ ] Buy dip\n"
        )
        ctx = parse_daily_note_sections(tmp_path, "2026-02-07")
        assert ctx is not None
        assert ctx.date == "2026-02-07"
        assert ctx.focus_items == ["Super Bowl party", "Finish project"]
        assert ctx.notes_items == ["Rachel is my girlfriend", "Try Trader Joe's miso black cod"]

    def test_handles_empty_sections(self, tmp_path):
        md = tmp_path / "2026-02-07.md"
        md.write_text("## Focus\n\n## Notes\n\n## Tasks\n- [ ] Something\n")
        ctx = parse_daily_note_sections(tmp_path, "2026-02-07")
        assert ctx is None  # No items in either section

    def test_missing_file_returns_none(self, tmp_path):
        ctx = parse_daily_note_sections(tmp_path, "2026-02-07")
        assert ctx is None

    def test_stops_at_next_heading(self, tmp_path):
        md = tmp_path / "2026-02-07.md"
        md.write_text("## Focus\n- Main focus\n## Notes\n- A note\n## Tasks\n- [ ] Not a note\n")
        ctx = parse_daily_note_sections(tmp_path, "2026-02-07")
        assert ctx is not None
        assert ctx.focus_items == ["Main focus"]
        assert ctx.notes_items == ["A note"]

    def test_ignores_empty_bullets(self, tmp_path):
        md = tmp_path / "2026-02-07.md"
        md.write_text("## Focus\n- Real item\n- \n## Notes\n- Note item\n")
        ctx = parse_daily_note_sections(tmp_path, "2026-02-07")
        assert ctx is not None
        assert ctx.focus_items == ["Real item"]
        assert ctx.notes_items == ["Note item"]

    def test_focus_only(self, tmp_path):
        md = tmp_path / "2026-02-07.md"
        md.write_text("## Focus\n- Just focus\n## Tasks\n- [ ] Stuff\n")
        ctx = parse_daily_note_sections(tmp_path, "2026-02-07")
        assert ctx is not None
        assert ctx.focus_items == ["Just focus"]
        assert ctx.notes_items == []

    def test_notes_only(self, tmp_path):
        md = tmp_path / "2026-02-07.md"
        md.write_text("## Notes\n- Just a note\n## Tasks\n- [ ] Stuff\n")
        ctx = parse_daily_note_sections(tmp_path, "2026-02-07")
        assert ctx is not None
        assert ctx.focus_items == []
        assert ctx.notes_items == ["Just a note"]


class TestFindRecentDailyContext:
    def test_finds_yesterday(self, tmp_path):
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        md = tmp_path / f"{yesterday}.md"
        md.write_text("## Focus\n- Yesterday's focus\n")
        ctx = find_recent_daily_context(tmp_path)
        assert ctx is not None
        assert ctx.date == yesterday
        assert ctx.focus_items == ["Yesterday's focus"]

    def test_skips_today(self, tmp_path):
        today = datetime.now().strftime("%Y-%m-%d")
        md = tmp_path / f"{today}.md"
        md.write_text("## Focus\n- Today's focus\n")
        ctx = find_recent_daily_context(tmp_path)
        assert ctx is None  # Today is skipped, nothing else found

    def test_lookback_finds_3_days_ago(self, tmp_path):
        """Monday briefing should find Friday's note (weekend gap)."""
        three_days_ago = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        md = tmp_path / f"{three_days_ago}.md"
        md.write_text("## Focus\n- Friday's focus\n")
        ctx = find_recent_daily_context(tmp_path)
        assert ctx is not None
        assert ctx.date == three_days_ago

    def test_no_notes_returns_none(self, tmp_path):
        ctx = find_recent_daily_context(tmp_path)
        assert ctx is None

    def test_skips_empty_content_notes(self, tmp_path):
        """Notes that exist but have empty Focus/Notes sections should be skipped."""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        # Yesterday has empty sections
        (tmp_path / f"{yesterday}.md").write_text("## Focus\n\n## Notes\n\n## Tasks\n")
        # Two days ago has content
        (tmp_path / f"{two_days_ago}.md").write_text("## Focus\n- Actual content\n")
        ctx = find_recent_daily_context(tmp_path)
        assert ctx is not None
        assert ctx.date == two_days_ago
        assert ctx.focus_items == ["Actual content"]

    def test_prefers_most_recent(self, tmp_path):
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        (tmp_path / f"{yesterday}.md").write_text("## Focus\n- Yesterday\n")
        (tmp_path / f"{two_days_ago}.md").write_text("## Focus\n- Two days ago\n")
        ctx = find_recent_daily_context(tmp_path)
        assert ctx is not None
        assert ctx.date == yesterday
