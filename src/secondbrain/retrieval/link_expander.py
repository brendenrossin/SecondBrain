"""Link expander: follow 1-hop wiki links from retrieved candidates."""

import logging
from dataclasses import dataclass

from secondbrain.retrieval.reranker import RankedCandidate
from secondbrain.stores.lexical import LexicalStore
from secondbrain.vault.links import extract_wiki_links

logger = logging.getLogger(__name__)


@dataclass
class LinkedContext:
    """A chunk fetched by following a wiki link from a retrieved candidate."""

    note_path: str
    note_title: str
    chunk_text: str
    linked_from: str  # note_title of the source candidate


class LinkExpander:
    """Expands retrieval results by following [[wiki links]] in candidates."""

    def __init__(self, lexical_store: LexicalStore) -> None:
        self._lexical_store = lexical_store

    def expand(
        self,
        ranked_candidates: list[RankedCandidate],
        max_linked: int = 3,
    ) -> list[LinkedContext]:
        """Parse wiki links from top candidates and fetch linked chunks.

        Args:
            ranked_candidates: Reranked candidates in score order.
            max_linked: Maximum number of linked chunks to return.

        Returns:
            List of LinkedContext from linked notes.
        """
        # Collect note_paths already in the candidate set
        candidate_paths: set[str] = {rc.candidate.note_path for rc in ranked_candidates}
        collected_paths: set[str] = set()
        results: list[LinkedContext] = []

        for rc in ranked_candidates:
            if len(results) >= max_linked:
                break

            titles = extract_wiki_links(rc.candidate.chunk_text)
            for title in titles:
                if len(results) >= max_linked:
                    break

                note_path = self._lexical_store.resolve_note_path(title)
                if note_path is None:
                    continue
                if note_path in candidate_paths or note_path in collected_paths:
                    continue

                chunk_data = self._lexical_store.get_first_chunk(note_path)
                if chunk_data is None:
                    continue

                collected_paths.add(note_path)
                results.append(
                    LinkedContext(
                        note_path=note_path,
                        note_title=chunk_data.get("note_title", title),
                        chunk_text=chunk_data["chunk_text"],
                        linked_from=rc.candidate.note_title,
                    )
                )

        return results
