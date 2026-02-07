"""Tests for the metadata extractor module."""

from unittest.mock import MagicMock

from secondbrain.extraction.extractor import (
    MetadataExtractor,
    _build_user_prompt,
    _content_hash,
    _normalize_date,
    _parse_result,
)
from secondbrain.models import Note


def _make_note(
    path: str = "notes/test.md",
    title: str = "Test Note",
    content: str = "Hello world.",
    frontmatter: dict | None = None,
) -> Note:
    return Note(
        path=path,
        title=title,
        content=content,
        frontmatter=frontmatter or {},
    )


class TestNormalizeDate:
    def test_iso_date(self) -> None:
        assert _normalize_date("2025-01-15") == "2025-01-15"

    def test_us_date(self) -> None:
        assert _normalize_date("01/15/2025") == "2025-01-15"

    def test_short_year(self) -> None:
        assert _normalize_date("3/5/25") == "2025-03-05"

    def test_no_date(self) -> None:
        assert _normalize_date("no date here") is None

    def test_embedded_date(self) -> None:
        assert _normalize_date("deadline is 2025-12-31 for the project") == "2025-12-31"


class TestContentHash:
    def test_deterministic(self) -> None:
        h1 = _content_hash("hello")
        h2 = _content_hash("hello")
        assert h1 == h2

    def test_different_content(self) -> None:
        assert _content_hash("a") != _content_hash("b")


class TestBuildUserPrompt:
    def test_basic_prompt(self) -> None:
        note = _make_note()
        prompt = _build_user_prompt(note)
        assert "Title: Test Note" in prompt
        assert "Hello world." in prompt

    def test_with_frontmatter(self) -> None:
        note = _make_note(frontmatter={"tags": ["python", "test"]})
        prompt = _build_user_prompt(note)
        assert "Frontmatter:" in prompt
        assert "tags" in prompt

    def test_truncation(self) -> None:
        note = _make_note(content="x" * 20000)
        prompt = _build_user_prompt(note, max_chars=100)
        assert "[... truncated ...]" in prompt
        assert len(prompt) < 20000


class TestParseResult:
    def test_full_result(self) -> None:
        raw = {
            "summary": "A test note about Python.",
            "key_phrases": ["python", "testing", "unit tests"],
            "entities": [
                {"text": "Python", "entity_type": "product", "confidence": 0.95},
            ],
            "dates": [
                {
                    "text": "2025-01-15",
                    "normalized_date": "2025-01-15",
                    "date_type": "deadline",
                    "confidence": 0.9,
                },
            ],
            "action_items": [
                {"text": "Write more tests", "confidence": 0.8, "priority": "medium"},
            ],
        }
        note = _make_note()
        result = _parse_result(raw, note, "test-model")

        assert result.summary == "A test note about Python."
        assert result.key_phrases == ["python", "testing", "unit tests"]
        assert len(result.entities) == 1
        assert result.entities[0].text == "Python"
        assert len(result.dates) == 1
        assert result.dates[0].normalized_date == "2025-01-15"
        assert len(result.action_items) == 1
        assert result.action_items[0].priority == "medium"
        assert result.note_path == "notes/test.md"
        assert result.model_used == "test-model"

    def test_empty_result(self) -> None:
        raw = {
            "summary": "",
            "key_phrases": [],
            "entities": [],
            "dates": [],
            "action_items": [],
        }
        note = _make_note()
        result = _parse_result(raw, note, "test-model")
        assert result.summary == ""
        assert result.key_phrases == []
        assert result.entities == []

    def test_missing_fields_defaults(self) -> None:
        raw = {"summary": "just a summary"}
        note = _make_note()
        result = _parse_result(raw, note, "test-model")
        assert result.summary == "just a summary"
        assert result.entities == []

    def test_date_normalization_fallback(self) -> None:
        raw = {
            "summary": "",
            "key_phrases": [],
            "entities": [],
            "dates": [
                {
                    "text": "01/15/2025",
                    "normalized_date": None,
                    "date_type": "event",
                    "confidence": 0.8,
                },
            ],
            "action_items": [],
        }
        note = _make_note()
        result = _parse_result(raw, note, "test-model")
        assert result.dates[0].normalized_date == "2025-01-15"


class TestMetadataExtractor:
    def test_extract_calls_llm(self) -> None:
        mock_client = MagicMock()
        mock_client.chat_json.return_value = {
            "summary": "Test summary",
            "key_phrases": ["test"],
            "entities": [],
            "dates": [],
            "action_items": [],
        }
        mock_client.model_name = "test-model"

        extractor = MetadataExtractor(mock_client)
        note = _make_note()
        result = extractor.extract(note)

        mock_client.chat_json.assert_called_once()
        assert result.summary == "Test summary"
        assert result.note_path == "notes/test.md"

    def test_extract_batch_with_progress(self) -> None:
        mock_client = MagicMock()
        mock_client.chat_json.return_value = {
            "summary": "Summary",
            "key_phrases": [],
            "entities": [],
            "dates": [],
            "action_items": [],
        }
        mock_client.model_name = "test-model"

        extractor = MetadataExtractor(mock_client)
        notes = [_make_note(path=f"note{i}.md") for i in range(3)]

        progress_calls: list[tuple[int, int, str]] = []
        results = extractor.extract_batch(
            notes,
            on_progress=lambda cur, total, path: progress_calls.append((cur, total, path)),
        )

        assert len(results) == 3
        assert len(progress_calls) == 3
        assert progress_calls[0] == (1, 3, "note0.md")

    def test_extract_batch_handles_failures(self) -> None:
        mock_client = MagicMock()
        call_count = 0

        def side_effect(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("LLM error")
            return {
                "summary": "OK",
                "key_phrases": [],
                "entities": [],
                "dates": [],
                "action_items": [],
            }

        mock_client.chat_json.side_effect = side_effect
        mock_client.model_name = "test-model"

        extractor = MetadataExtractor(mock_client)
        notes = [_make_note(path=f"note{i}.md") for i in range(3)]
        results = extractor.extract_batch(notes)

        # 2 succeed, 1 fails
        assert len(results) == 2
