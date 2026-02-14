"""Functional tests for indexing/chunker.py — heading hierarchy, splitting, and chunk ID stability."""

from secondbrain.indexing.chunker import Chunker
from secondbrain.models import Note


def _make_note(content: str, path: str = "test.md", title: str = "Test") -> Note:
    return Note(path=path, title=title, content=content, frontmatter={})


class TestHeadingHierarchy:
    """Tests for _split_by_headings heading path tracking."""

    def test_single_h1(self):
        chunker = Chunker(target_size=2000)
        sections = chunker._split_by_headings("# Title\n\nContent under title.")
        # One section: heading path = ["Title"], content = "Content under title."
        assert len(sections) == 1
        assert sections[0][0] == ["Title"]
        assert "Content under title." in sections[0][1]

    def test_nested_h1_h2_h3(self):
        chunker = Chunker(target_size=2000)
        content = "# H1\n\nH1 content.\n\n## H2\n\nH2 content.\n\n### H3\n\nH3 content."
        sections = chunker._split_by_headings(content)
        paths = [s[0] for s in sections]
        assert ["H1"] in paths
        assert ["H1", "H2"] in paths
        assert ["H1", "H2", "H3"] in paths

    def test_heading_level_reset(self):
        """When going from H3 back to H2, the path should reset."""
        chunker = Chunker(target_size=2000)
        content = "# Title\n\n## Section A\n\n### Sub A\n\nA content.\n\n## Section B\n\nB content."
        sections = chunker._split_by_headings(content)
        paths = [s[0] for s in sections]
        assert ["Title", "Section A", "Sub A"] in paths
        assert ["Title", "Section B"] in paths
        # Section B should NOT have "Sub A" in its path
        for path, _ in sections:
            if "Section B" in path:
                assert "Sub A" not in path

    def test_content_before_first_heading(self):
        chunker = Chunker(target_size=2000)
        content = "Preamble text.\n\n# Heading\n\nHeading content."
        sections = chunker._split_by_headings(content)
        # First section has empty path (preamble)
        assert sections[0][0] == []
        assert "Preamble text." in sections[0][1]

    def test_trailing_content_after_last_heading(self):
        chunker = Chunker(target_size=2000)
        content = "# Heading\n\nContent after heading with trailing text."
        sections = chunker._split_by_headings(content)
        assert len(sections) == 1
        assert "trailing text" in sections[0][1]

    def test_no_headings(self):
        chunker = Chunker(target_size=2000)
        content = "Just plain text with no markdown headings at all."
        sections = chunker._split_by_headings(content)
        assert len(sections) == 1
        assert sections[0][0] == []

    def test_empty_content(self):
        chunker = Chunker(target_size=2000)
        sections = chunker._split_by_headings("")
        assert sections == []

    def test_all_six_heading_levels(self):
        chunker = Chunker(target_size=2000)
        content = "# L1\n\n## L2\n\n### L3\n\n#### L4\n\n##### L5\n\n###### L6\n\nDeep content."
        sections = chunker._split_by_headings(content)
        deepest = sections[-1]
        assert deepest[0] == ["L1", "L2", "L3", "L4", "L5", "L6"]


class TestChunkNote:
    """Tests for the full chunk_note pipeline."""

    def test_small_note_single_chunk(self):
        chunker = Chunker(target_size=700, min_chunk_size=10)
        note = _make_note("# Title\n\nA short note with enough content to pass min_chunk_size.")
        chunks = chunker.chunk_note(note)
        assert len(chunks) == 1
        assert chunks[0].heading_path == ["Title"]

    def test_large_note_splits(self):
        chunker = Chunker(target_size=200, min_chunk_size=50)
        paragraphs = "\n\n".join([f"Paragraph {i} with enough text to matter." for i in range(20)])
        note = _make_note(f"# Title\n\n{paragraphs}")
        chunks = chunker.chunk_note(note)
        assert len(chunks) > 1

    def test_min_chunk_size_filters_small_chunks(self):
        chunker = Chunker(target_size=700, min_chunk_size=100)
        note = _make_note("# Title\n\nTiny.")
        chunks = chunker.chunk_note(note)
        # "Tiny." is only 5 chars, below min_chunk_size — should be filtered
        assert len(chunks) == 0

    def test_chunk_index_sequential(self):
        chunker = Chunker(target_size=200, min_chunk_size=10)
        paragraphs = "\n\n".join([f"Paragraph {i} " + "x" * 100 for i in range(10)])
        note = _make_note(f"# Title\n\n{paragraphs}")
        chunks = chunker.chunk_note(note)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_note_path_and_title_preserved(self):
        chunker = Chunker(target_size=700, min_chunk_size=10)
        note = _make_note(
            "# My Note\n\nContent that is long enough to pass the minimum chunk size filter.",
            path="folder/my-note.md",
            title="My Note",
        )
        chunks = chunker.chunk_note(note)
        assert all(c.note_path == "folder/my-note.md" for c in chunks)
        assert all(c.note_title == "My Note" for c in chunks)

    def test_heading_path_assigned_to_chunks(self):
        chunker = Chunker(target_size=2000, min_chunk_size=10)
        content = "# Title\n\n## Section\n\n" + "Content " * 30
        note = _make_note(content)
        chunks = chunker.chunk_note(note)
        # The chunk under ## Section should have path ["Title", "Section"]
        section_chunks = [c for c in chunks if "Section" in c.heading_path]
        assert len(section_chunks) > 0


class TestChunkIdStability:
    """Tests that chunk IDs are deterministic and stable."""

    def test_same_input_same_id(self):
        chunker = Chunker(target_size=700, min_chunk_size=10)
        note = _make_note("# Title\n\nSome content that is long enough to pass the minimum size.")
        chunks_a = chunker.chunk_note(note)
        chunks_b = chunker.chunk_note(note)
        assert [c.chunk_id for c in chunks_a] == [c.chunk_id for c in chunks_b]

    def test_different_content_different_id(self):
        chunker = Chunker(target_size=700, min_chunk_size=10)
        note_a = _make_note(
            "# Title\n\nContent version A is long enough for a chunk to be created."
        )
        note_b = _make_note(
            "# Title\n\nContent version B is long enough for a chunk to be created."
        )
        chunks_a = chunker.chunk_note(note_a)
        chunks_b = chunker.chunk_note(note_b)
        assert chunks_a[0].chunk_id != chunks_b[0].chunk_id

    def test_whitespace_normalization_same_checksum(self):
        chunker = Chunker()
        text_a = "Hello   world   with   spaces"
        text_b = "Hello world with spaces"
        assert chunker._generate_checksum(text_a) == chunker._generate_checksum(text_b)


class TestForceSplit:
    """Tests for the force split with overlap."""

    def test_force_split_respects_word_boundary(self):
        chunker = Chunker(target_size=50, overlap=10)
        text = "word " * 30  # 150 chars
        parts = chunker._force_split(text)
        # Each part should not break mid-word
        for part in parts:
            assert not part.startswith(" ")

    def test_force_split_creates_overlap(self):
        chunker = Chunker(target_size=100, overlap=20)
        text = "abcdefghij " * 30  # ~330 chars
        parts = chunker._force_split(text)
        assert len(parts) > 1
        # Check overlap exists: end of first part should appear in start of second
        if len(parts) >= 2:
            end_of_first = parts[0][-20:]
            assert any(c in parts[1] for c in end_of_first.split())
