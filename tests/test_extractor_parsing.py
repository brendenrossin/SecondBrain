"""MetadataExtractor result parsing tests."""

from unittest.mock import MagicMock

import pytest

from secondbrain.extraction.extractor import MetadataExtractor, _parse_result
from secondbrain.models import Note


def _make_note(path="notes/test.md", title="Test", content="Hello."):
    return Note(path=path, title=title, content=content, frontmatter={})


# ---------------------------------------------------------------------------
# _parse_result completeness
# ---------------------------------------------------------------------------


class TestParseResultComplete:
    def test_all_fields_populated(self):
        note = _make_note()
        raw = {
            "summary": "A note about AI research.",
            "key_phrases": ["machine learning", "neural networks"],
            "entities": [
                {"text": "OpenAI", "entity_type": "org", "confidence": 0.95},
            ],
            "dates": [
                {
                    "text": "2026-01-15",
                    "normalized_date": "2026-01-15",
                    "date_type": "event",
                    "confidence": 0.9,
                }
            ],
            "action_items": [{"text": "Review the paper", "confidence": 0.8, "priority": "high"}],
        }
        result = _parse_result(raw, note, model_used="gpt-4o-mini")

        assert result.summary == "A note about AI research."
        assert result.key_phrases == ["machine learning", "neural networks"]
        assert len(result.entities) == 1
        assert result.entities[0].text == "OpenAI"
        assert result.entities[0].entity_type == "org"
        assert result.entities[0].confidence == pytest.approx(0.95)
        assert len(result.dates) == 1
        assert result.dates[0].normalized_date == "2026-01-15"
        assert result.dates[0].date_type == "event"
        assert len(result.action_items) == 1
        assert result.action_items[0].text == "Review the paper"
        assert result.action_items[0].priority == "high"
        assert result.model_used == "gpt-4o-mini"
        assert result.note_path == note.path

    def test_empty_optional_fields(self):
        note = _make_note()
        raw = {"summary": "Minimal note.", "key_phrases": []}
        result = _parse_result(raw, note, model_used="gpt-4o-mini")

        assert result.summary == "Minimal note."
        assert result.key_phrases == []
        assert result.entities == []
        assert result.dates == []
        assert result.action_items == []

    def test_missing_fields_default_gracefully(self):
        note = _make_note()
        result = _parse_result({}, note, model_used="gpt-4o-mini")

        assert result.summary == ""
        assert result.key_phrases == []
        assert result.entities == []
        assert result.dates == []
        assert result.action_items == []

    def test_malformed_entity_skipped(self):
        """Strings and dicts with missing keys should not crash; valid entries kept."""
        note = _make_note()
        raw = {
            "entities": [
                {"text": "Alice", "entity_type": "person", "confidence": 0.9},
                "this is a plain string",  # skipped — not a dict
                {"entity_type": "org"},  # missing "text" → uses default ""
            ]
        }
        result = _parse_result(raw, note, model_used="gpt-4o-mini")

        # Plain string is skipped; dicts (even with missing keys) are kept
        assert len(result.entities) == 2
        assert result.entities[0].text == "Alice"
        assert result.entities[1].text == ""  # default for missing key

    def test_null_priority_handled(self):
        note = _make_note()
        raw = {"action_items": [{"text": "Do something", "confidence": 0.7, "priority": None}]}
        result = _parse_result(raw, note, model_used="gpt-4o-mini")

        assert len(result.action_items) == 1
        assert result.action_items[0].priority is None

    def test_date_normalization_fallback(self):
        """When normalized_date is None but text contains a parseable date, regex extracts it."""
        note = _make_note()
        raw = {
            "dates": [
                {
                    "text": "Meeting on 2026-05-20",
                    "normalized_date": None,
                    "date_type": "event",
                    "confidence": 0.85,
                }
            ]
        }
        result = _parse_result(raw, note, model_used="gpt-4o-mini")

        assert len(result.dates) == 1
        assert result.dates[0].normalized_date == "2026-05-20"

    def test_model_used_reflects_input(self):
        note = _make_note()
        for model in ("gpt-4o-mini", "claude-3-haiku", "llama3.2:3b"):
            result = _parse_result({}, note, model_used=model)
            assert result.model_used == model


# ---------------------------------------------------------------------------
# extract_batch resilience
# ---------------------------------------------------------------------------


class TestExtractBatchResilience:
    def _make_extractor(self, side_effects):
        """Build a MetadataExtractor whose extract() follows the given side_effects list."""
        mock_client = MagicMock()
        mock_client.model_name = "gpt-4o-mini"
        extractor = MetadataExtractor(llm_client=mock_client)
        extractor.extract = MagicMock(side_effect=side_effects)
        return extractor

    def test_skips_failures_continues(self):
        """2nd note raises; results for 1st and 3rd are still returned."""
        notes = [
            _make_note(path="notes/a.md", title="A"),
            _make_note(path="notes/b.md", title="B"),
            _make_note(path="notes/c.md", title="C"),
        ]

        # Pre-build NoteMetadata stubs for A and C using _parse_result
        meta_a = _parse_result({"summary": "A"}, notes[0], "gpt-4o-mini")
        meta_c = _parse_result({"summary": "C"}, notes[2], "gpt-4o-mini")

        extractor = self._make_extractor(side_effects=[meta_a, RuntimeError("LLM timeout"), meta_c])

        results = extractor.extract_batch(notes)

        assert len(results) == 2
        assert results[0].note_path == "notes/a.md"
        assert results[1].note_path == "notes/c.md"

    def test_progress_callback_called(self):
        """on_progress receives (i, total, path) for each note."""
        notes = [
            _make_note(path="notes/x.md", title="X"),
            _make_note(path="notes/y.md", title="Y"),
        ]
        meta_x = _parse_result({"summary": "X"}, notes[0], "gpt-4o-mini")
        meta_y = _parse_result({"summary": "Y"}, notes[1], "gpt-4o-mini")

        extractor = self._make_extractor(side_effects=[meta_x, meta_y])
        progress_calls = []
        extractor.extract_batch(notes, on_progress=lambda i, t, p: progress_calls.append((i, t, p)))

        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2, "notes/x.md")
        assert progress_calls[1] == (2, 2, "notes/y.md")
