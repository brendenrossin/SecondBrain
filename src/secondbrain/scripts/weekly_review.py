"""Weekly review generator: assembles a template-based weekly summary from daily notes."""

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from secondbrain.scripts.task_aggregator import (
    AggregatedTask,
    aggregate_tasks,
    parse_daily_note_sections,
    scan_daily_notes,
)

logger = logging.getLogger(__name__)

# Common English stopwords to exclude from recurring topic detection
STOPWORDS = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "get",
        "got",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "let",
        "like",
        "me",
        "might",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "re",
        "same",
        "she",
        "should",
        "so",
        "some",
        "still",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "us",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "also",
        "going",
        "really",
        "think",
        "went",
        "today",
        "tomorrow",
        "yesterday",
        "need",
        "new",
        "one",
        "two",
        "three",
    ]
)


@dataclass
class WeekData:
    """Collected data for a single week."""

    week_key: str  # e.g. "2026-W06"
    start_date: date
    end_date: date
    focus_items: list[tuple[str, list[str]]]  # (item, [day_names])
    completed_tasks: list[AggregatedTask]
    open_tasks: list[AggregatedTask]
    notes_items: list[tuple[str, str]]  # (item, date_str)
    recurring_topics: list[str]


def generate_weekly_review(vault_path: Path, target_date: date | None = None) -> str:
    """Generate a weekly review note for the ISO week containing target_date.

    Args:
        vault_path: Path to the Obsidian vault root.
        target_date: Any date in the target week. Defaults to today.

    Returns:
        Summary string of action taken.
    """
    if target_date is None:
        target_date = date.today()

    start, end, week_key = _get_week_boundaries(target_date)
    daily_dir = vault_path / "00_Daily"
    week_data = _collect_week_data(daily_dir, start, end, week_key)
    content = _render_weekly_note(week_data)

    weekly_dir = vault_path / "00_Weekly"
    weekly_dir.mkdir(parents=True, exist_ok=True)
    output_file = weekly_dir / f"{week_key}.md"
    output_file.write_text(content, encoding="utf-8")

    logger.info("Wrote weekly review: %s", output_file)
    return f"Generated weekly review: {week_key} -> 00_Weekly/{week_key}.md"


def _get_week_boundaries(target: date) -> tuple[date, date, str]:
    """Calculate ISO week boundaries (Monday–Sunday) for a given date.

    Returns:
        (start_date, end_date, week_key) where week_key is "YYYY-WNN".
    """
    iso_year, iso_week, _ = target.isocalendar()
    # Monday of that ISO week
    start = date.fromisocalendar(iso_year, iso_week, 1)
    end = start + timedelta(days=6)
    week_key = f"{iso_year}-W{iso_week:02d}"
    return start, end, week_key


def _collect_week_data(daily_dir: Path, start: date, end: date, week_key: str) -> WeekData:
    """Scan daily notes for the given week and collect all data."""
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # Collect focus items with day tracking
    focus_map: dict[str, list[str]] = {}  # item -> [day_names]
    notes_items: list[tuple[str, str]] = []
    all_word_counts: Counter[str] = Counter()
    days_with_word: dict[str, set[int]] = {}  # word -> set of day indices

    for i in range(7):
        day = start + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        ctx = parse_daily_note_sections(daily_dir, date_str)
        if ctx is None:
            continue

        for item in ctx.focus_items:
            focus_map.setdefault(item, []).append(day_names[i])

        for item in ctx.notes_items:
            notes_items.append((item, date_str))

        # Track words for recurring topics
        all_text = " ".join(ctx.focus_items + ctx.notes_items)
        words = _extract_words(all_text)
        for word in set(words):  # unique per day
            all_word_counts[word] += 1
            days_with_word.setdefault(word, set()).add(i)

    # Get tasks for this week
    all_tasks = scan_daily_notes(daily_dir)
    week_start_str = start.strftime("%Y-%m-%d")
    week_end_str = end.strftime("%Y-%m-%d")

    # Filter tasks to those appearing in this week
    week_tasks = [t for t in all_tasks if week_start_str <= t.source_date <= week_end_str]
    aggregated = aggregate_tasks(week_tasks)

    completed = [t for t in aggregated if t.completed]
    open_tasks = [t for t in aggregated if not t.completed]

    # Recurring topics: words appearing across 3+ daily notes
    recurring = [
        word
        for word, count in all_word_counts.most_common()
        if len(days_with_word.get(word, set())) >= 3
    ][:10]

    focus_items = list(focus_map.items())

    return WeekData(
        week_key=week_key,
        start_date=start,
        end_date=end,
        focus_items=focus_items,
        completed_tasks=completed,
        open_tasks=open_tasks,
        notes_items=notes_items,
        recurring_topics=recurring,
    )


def _extract_words(text: str) -> list[str]:
    """Extract meaningful words from text, excluding stopwords and short words."""
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]


def _render_weekly_note(data: WeekData) -> str:
    """Render the weekly review as markdown with frontmatter."""
    start_str = data.start_date.strftime("%Y-%m-%d")
    end_str = data.end_date.strftime("%Y-%m-%d")
    generated = datetime.now().strftime("%Y-%m-%d")

    # Human-readable date range
    start_display = data.start_date.strftime("%b %-d")
    end_display = data.end_date.strftime("%b %-d, %Y")
    iso_week_num = data.start_date.isocalendar()[1]

    lines = [
        "---",
        "type: weekly",
        f"week: {data.week_key}",
        f"start_date: {start_str}",
        f"end_date: {end_str}",
        f"generated: {generated}",
        "---",
        "",
        f"# Week {iso_week_num} — {start_display}–{end_display}",
        "",
    ]

    # Focus Areas
    lines.append("## Focus Areas")
    if data.focus_items:
        for item, days in data.focus_items:
            day_list = ", ".join(days)
            lines.append(f"- {item} ({day_list})")
    else:
        lines.append("- *No focus items recorded*")
    lines.append("")

    # Completed Tasks
    lines.append("## Completed")
    if data.completed_tasks:
        by_cat: dict[str, list[AggregatedTask]] = {}
        for task in data.completed_tasks:
            cat = task.category or "Uncategorized"
            by_cat.setdefault(cat, []).append(task)
        for cat in sorted(by_cat):
            lines.append(f"### {cat}")
            for task in by_cat[cat]:
                lines.append(f"- {task.text}")
        lines.append("")
    else:
        lines.append("- *No tasks completed*")
        lines.append("")

    # Still Open
    lines.append("## Still Open")
    if data.open_tasks:
        by_cat_open: dict[str, list[AggregatedTask]] = {}
        for task in data.open_tasks:
            cat = task.category or "Uncategorized"
            by_cat_open.setdefault(cat, []).append(task)
        for cat in sorted(by_cat_open):
            lines.append(f"### {cat}")
            for task in by_cat_open[cat]:
                due_suffix = f" (due: {task.due_date})" if task.due_date else ""
                lines.append(f"- [ ] {task.text}{due_suffix}")
        lines.append("")
    else:
        lines.append("- *All tasks completed!*")
        lines.append("")

    # Notes & Observations
    lines.append("## Notes & Observations")
    if data.notes_items:
        for item, _date_str in data.notes_items:
            lines.append(f"- {item}")
    else:
        lines.append("- *No notes recorded*")
    lines.append("")

    # Recurring Topics
    lines.append("## Recurring Topics")
    if data.recurring_topics:
        lines.append(", ".join(data.recurring_topics))
    else:
        lines.append("*No recurring topics detected*")
    lines.append("")

    return "\n".join(lines)
