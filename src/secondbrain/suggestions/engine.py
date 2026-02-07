"""Suggestion engine: related notes, link suggestions, tag suggestions."""

import logging
from datetime import UTC, datetime

from secondbrain.indexing.embedder import Embedder
from secondbrain.models import (
    LinkSuggestion,
    NoteMetadata,
    NoteSuggestions,
    RelatedNote,
    TagSuggestion,
)
from secondbrain.stores.metadata import MetadataStore
from secondbrain.stores.vector import VectorStore

logger = logging.getLogger(__name__)


def _title_from_path(note_path: str) -> str:
    """Extract a display title from a note path."""
    return note_path.rsplit("/", 1)[-1].replace(".md", "")


class SuggestionEngine:
    """Generate suggestions for a note: related notes, links, tags."""

    def __init__(
        self,
        vector_store: VectorStore,
        metadata_store: MetadataStore,
        embedder: Embedder,
    ) -> None:
        self.vector_store = vector_store
        self.metadata_store = metadata_store
        self.embedder = embedder

    def suggest(self, note_path: str) -> NoteSuggestions | None:
        """Generate suggestions for a note.

        Returns None if the note has no extracted metadata.
        """
        source_meta = self.metadata_store.get(note_path)
        if source_meta is None:
            return None

        note_title = _title_from_path(note_path)

        related = self._find_related(note_path, source_meta, note_title)
        links = self._suggest_links(note_path, source_meta, related)
        tags = self._suggest_tags(source_meta, related)

        return NoteSuggestions(
            note_path=note_path,
            note_title=note_title,
            related_notes=related,
            suggested_links=links,
            suggested_tags=tags,
            generated_at=datetime.now(UTC).isoformat(),
        )

    def _find_related(
        self, note_path: str, source_meta: NoteMetadata, note_title: str
    ) -> list[RelatedNote]:
        """Find related notes via vector similarity on title + summary."""
        query_text = f"{note_title}: {source_meta.summary}"
        query_embedding = self.embedder.embed_query(query_text)

        results = self.vector_store.search(query_embedding, top_k=50)

        # Deduplicate by note_path and exclude the source note
        seen: dict[str, float] = {}
        for _chunk_id, similarity, metadata, _document in results:
            result_path = str(metadata.get("note_path", ""))
            if result_path == note_path:
                continue
            if result_path not in seen or similarity > seen[result_path]:
                seen[result_path] = similarity

        # Build RelatedNote list with shared entities
        source_entities = {e.text.lower() for e in source_meta.entities}

        related: list[RelatedNote] = []
        for path, sim in sorted(seen.items(), key=lambda x: x[1], reverse=True)[:10]:
            title = _title_from_path(path)
            target_meta = self.metadata_store.get(path)
            shared = [
                e.text
                for e in (target_meta.entities if target_meta else [])
                if e.text.lower() in source_entities
            ]

            related.append(
                RelatedNote(
                    note_path=path,
                    note_title=title,
                    similarity_score=round(sim, 4),
                    shared_entities=shared,
                )
            )

        return related

    def _suggest_links(
        self,
        note_path: str,
        source_meta: NoteMetadata,
        related: list[RelatedNote],
    ) -> list[LinkSuggestion]:
        """Suggest wiki-links based on entity/title overlap with other notes."""
        suggestions: list[LinkSuggestion] = []
        source_entities = {e.text.lower(): e for e in source_meta.entities}

        # Build title-to-path mapping for entity-title matching
        title_to_path: dict[str, str] = {
            _title_from_path(meta.note_path).lower(): meta.note_path
            for meta in self.metadata_store.get_all()
            if meta.note_path != note_path
        }

        # Suggest links from shared entities in related notes
        for rel in related:
            if not rel.shared_entities:
                continue
            for entity_text in rel.shared_entities[:2]:
                suggestions.append(
                    LinkSuggestion(
                        target_note_path=rel.note_path,
                        target_note_title=rel.note_title,
                        anchor_text=entity_text,
                        confidence=rel.similarity_score,
                        reason=f"Shared entity: {entity_text}",
                    )
                )

        # Suggest links where source entities match other note titles
        for entity_lower, entity in source_entities.items():
            if entity_lower in title_to_path:
                target_path = title_to_path[entity_lower]
                target_title = _title_from_path(target_path)
                # Avoid duplicates
                if not any(s.target_note_path == target_path for s in suggestions):
                    suggestions.append(
                        LinkSuggestion(
                            target_note_path=target_path,
                            target_note_title=target_title,
                            anchor_text=entity.text,
                            confidence=entity.confidence,
                            reason=f"Entity matches note title: {entity.text}",
                        )
                    )

        # Deduplicate and limit
        seen_targets: set[str] = set()
        deduped: list[LinkSuggestion] = []
        for s in sorted(suggestions, key=lambda x: x.confidence, reverse=True):
            key = f"{s.target_note_path}:{s.anchor_text}"
            if key not in seen_targets:
                seen_targets.add(key)
                deduped.append(s)
            if len(deduped) >= 10:
                break

        return deduped

    def _suggest_tags(
        self, source_meta: NoteMetadata, related: list[RelatedNote]
    ) -> list[TagSuggestion]:
        """Suggest tags based on key phrases from similar notes."""
        tag_scores: dict[str, float] = {}
        tag_sources: dict[str, list[str]] = {}

        for rel in related:
            rel_meta = self.metadata_store.get(rel.note_path)
            if not rel_meta:
                continue
            for phrase in rel_meta.key_phrases:
                tag = phrase.lower().strip()
                if not tag:
                    continue
                tag_scores[tag] = tag_scores.get(tag, 0.0) + rel.similarity_score
                tag_sources.setdefault(tag, []).append(rel.note_path)

        source_phrases = {kp.lower().strip() for kp in source_meta.key_phrases}

        ranked_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)

        suggestions: list[TagSuggestion] = []
        for tag, weighted_score in ranked_tags[:20]:
            if tag in source_phrases:
                continue
            # Normalize confidence: divide by number of related notes to get 0-1 range
            confidence = min(weighted_score / max(len(related), 1), 1.0)
            suggestions.append(
                TagSuggestion(
                    tag=tag,
                    confidence=round(confidence, 3),
                    source_notes=tag_sources.get(tag, [])[:5],
                )
            )
            if len(suggestions) >= 10:
                break

        return suggestions
