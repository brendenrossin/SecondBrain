"""LLM-based metadata extractor for vault notes."""

import hashlib
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from secondbrain.models import (
    ActionItem,
    DateMention,
    Entity,
    Note,
    NoteMetadata,
)
from secondbrain.scripts.llm_client import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a metadata extraction assistant. Given a Markdown note, extract structured metadata.

Return valid JSON with exactly these fields:
{
  "summary": "1-2 sentence summary of the note's main topic",
  "key_phrases": ["phrase1", "phrase2", ...],
  "entities": [
    {"text": "entity name", "entity_type": "person|org|product|place", "confidence": 0.0-1.0}
  ],
  "dates": [
    {"text": "original text", "normalized_date": "YYYY-MM-DD or null", "date_type": "deadline|event|reference", "confidence": 0.0-1.0}
  ],
  "action_items": [
    {"text": "action item text", "confidence": 0.0-1.0, "priority": "high|medium|low|null"}
  ]
}

Rules:
- key_phrases: 3-10 important phrases or topics from the note
- entities: people, organizations, products, places mentioned. Only include clear mentions.
- dates: any date references. Normalize to YYYY-MM-DD when possible. Set null if ambiguous.
- action_items: tasks, TODOs, follow-ups. Look for checkbox items, "should", "need to", "TODO".
- Confidence scores: 0.0-1.0 indicating your certainty about the extraction.
- Return ONLY valid JSON, no markdown fences or extra text.\
"""


def _build_user_prompt(note: Note, max_chars: int = 12000) -> str:
    """Build the user prompt from a note, truncating if needed."""
    content = note.content
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[... truncated ...]"

    frontmatter_str = ""
    if note.frontmatter:
        fm_parts = [f"  {k}: {v}" for k, v in note.frontmatter.items()]
        frontmatter_str = "Frontmatter:\n" + "\n".join(fm_parts) + "\n\n"

    return f"Title: {note.title}\nPath: {note.path}\n\n{frontmatter_str}Content:\n{content}"


def _content_hash(content: str) -> str:
    """Compute SHA-1 hash of note content."""
    return hashlib.sha1(content.encode()).hexdigest()


_DATE_PATTERN = re.compile(
    r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"
    r"|\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b"
)


def _normalize_date(text: str) -> str | None:
    """Try to normalize a date string to YYYY-MM-DD."""
    m = _DATE_PATTERN.search(text)
    if m:
        if m.group(1):  # YYYY-MM-DD
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        if m.group(4):  # MM/DD/YYYY
            year = m.group(6)
            if len(year) == 2:
                year = "20" + year
            return f"{year}-{int(m.group(4)):02d}-{int(m.group(5)):02d}"
    return None


def _parse_result(raw: dict[str, Any], note: Note, model_used: str) -> NoteMetadata:
    """Parse LLM JSON response into a NoteMetadata model."""
    entities = []
    for e in raw.get("entities", []):
        if isinstance(e, dict):
            entities.append(Entity(
                text=str(e.get("text", "")),
                entity_type=str(e.get("entity_type", "unknown")),
                confidence=float(e.get("confidence", 0.5)),
            ))

    dates = []
    for d in raw.get("dates", []):
        if isinstance(d, dict):
            text = str(d.get("text", ""))
            normalized = d.get("normalized_date")
            if normalized is None:
                normalized = _normalize_date(text)
            dates.append(DateMention(
                text=text,
                normalized_date=str(normalized) if normalized else None,
                date_type=str(d.get("date_type", "reference")),
                confidence=float(d.get("confidence", 0.5)),
            ))

    action_items = []
    for a in raw.get("action_items", []):
        if isinstance(a, dict):
            priority_val = a.get("priority")
            action_items.append(ActionItem(
                text=str(a.get("text", "")),
                confidence=float(a.get("confidence", 0.5)),
                priority=str(priority_val) if priority_val else None,
            ))

    key_phrases_raw = raw.get("key_phrases", [])
    key_phrases = [str(kp) for kp in key_phrases_raw] if isinstance(key_phrases_raw, list) else []

    return NoteMetadata(
        note_path=note.path,
        summary=str(raw.get("summary", "")),
        key_phrases=key_phrases,
        entities=entities,
        dates=dates,
        action_items=action_items,
        extracted_at=datetime.now(UTC).isoformat(),
        content_hash=_content_hash(note.content),
        model_used=model_used,
    )


class MetadataExtractor:
    """Extract structured metadata from notes using LLM."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def extract(self, note: Note) -> NoteMetadata:
        """Extract metadata from a single note via one LLM call."""
        user_prompt = _build_user_prompt(note)
        result = self.llm_client.chat_json(SYSTEM_PROMPT, user_prompt)
        return _parse_result(result, note, self.llm_client.model_name)

    def extract_batch(
        self,
        notes: list[Note],
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> list[NoteMetadata]:
        """Extract metadata for multiple notes, skipping failures."""
        results: list[NoteMetadata] = []
        total = len(notes)
        for i, note in enumerate(notes):
            if on_progress:
                on_progress(i + 1, total, note.path)
            try:
                metadata = self.extract(note)
                results.append(metadata)
            except Exception:
                logger.warning("Failed to extract metadata for %s", note.path, exc_info=True)
        return results
