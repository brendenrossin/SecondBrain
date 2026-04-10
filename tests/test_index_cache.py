"""Tests for IndexCache — blurb and embedding caching."""

from pathlib import Path

import numpy as np
import pytest

from secondbrain.stores.index_cache import IndexCache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cache(tmp_path: Path) -> IndexCache:
    return IndexCache(tmp_path / "index_cache.db")


# ---------------------------------------------------------------------------
# Blurb cache
# ---------------------------------------------------------------------------


class TestBlurbCache:
    def test_blurb_cache_miss_returns_none(self, cache: IndexCache) -> None:
        result = cache.get_blurb("nonexistent_hash", "gpt-4o-mini")
        assert result is None

    def test_blurb_cache_set_and_get(self, cache: IndexCache) -> None:
        cache.set_blurb("abc123", "gpt-4o-mini", "This chunk is about Python typing.")
        result = cache.get_blurb("abc123", "gpt-4o-mini")
        assert result == "This chunk is about Python typing."

    def test_blurb_cache_different_models(self, cache: IndexCache) -> None:
        cache.set_blurb("abc123", "gpt-4o-mini", "Mini blurb")
        cache.set_blurb("abc123", "gpt-4o", "Full blurb")
        assert cache.get_blurb("abc123", "gpt-4o-mini") == "Mini blurb"
        assert cache.get_blurb("abc123", "gpt-4o") == "Full blurb"

    def test_blurb_cache_overwrite(self, cache: IndexCache) -> None:
        """INSERT OR REPLACE should overwrite an existing entry."""
        cache.set_blurb("abc123", "gpt-4o-mini", "First blurb")
        cache.set_blurb("abc123", "gpt-4o-mini", "Updated blurb")
        assert cache.get_blurb("abc123", "gpt-4o-mini") == "Updated blurb"


# ---------------------------------------------------------------------------
# Embedding cache
# ---------------------------------------------------------------------------


class TestEmbeddingCache:
    def test_embedding_cache_miss_returns_none(self, cache: IndexCache) -> None:
        result = cache.get_embedding("nonexistent_hash", "text-embedding-3-small")
        assert result is None

    def test_embedding_cache_set_and_get(self, cache: IndexCache) -> None:
        embedding = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        cache.set_embedding("abc123", "text-embedding-3-small", embedding)
        result = cache.get_embedding("abc123", "text-embedding-3-small")
        assert result is not None
        np.testing.assert_array_almost_equal(result, embedding)

    def test_embedding_roundtrip_preserves_dtype(self, cache: IndexCache) -> None:
        embedding = np.array([1.0, -0.5, 0.0, 0.123456], dtype=np.float32)
        cache.set_embedding("hash1", "model-a", embedding)
        result = cache.get_embedding("hash1", "model-a")
        assert result is not None
        assert result.dtype == np.float32

    def test_embedding_cache_different_models(self, cache: IndexCache) -> None:
        emb_a = np.array([1.0, 0.0], dtype=np.float32)
        emb_b = np.array([0.0, 1.0], dtype=np.float32)
        cache.set_embedding("hash1", "model-a", emb_a)
        cache.set_embedding("hash1", "model-b", emb_b)
        np.testing.assert_array_equal(cache.get_embedding("hash1", "model-a"), emb_a)
        np.testing.assert_array_equal(cache.get_embedding("hash1", "model-b"), emb_b)

    def test_embedding_cache_large_vector(self, cache: IndexCache) -> None:
        """Ensure large-dimensional embeddings (768-d) round-trip correctly."""
        rng = np.random.default_rng(42)
        embedding = rng.standard_normal(768).astype(np.float32)
        cache.set_embedding("hashbig", "bge-base", embedding)
        result = cache.get_embedding("hashbig", "bge-base")
        assert result is not None
        assert result.shape == (768,)
        np.testing.assert_array_almost_equal(result, embedding)


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_removes_all(self, cache: IndexCache) -> None:
        cache.set_blurb("h1", "model", "blurb text")
        cache.set_embedding("h1", "model", np.array([0.5, 0.5], dtype=np.float32))
        cache.clear()
        assert cache.get_blurb("h1", "model") is None
        assert cache.get_embedding("h1", "model") is None

    def test_clear_empties_both_tables_independently(self, cache: IndexCache) -> None:
        """After clear, inserts into one table don't affect the other."""
        cache.set_blurb("h1", "m", "blurb")
        cache.set_embedding("h1", "m", np.array([1.0], dtype=np.float32))
        cache.clear()
        # Re-insert only blurb
        cache.set_blurb("h1", "m", "new blurb")
        assert cache.get_blurb("h1", "m") == "new blurb"
        assert cache.get_embedding("h1", "m") is None


# ---------------------------------------------------------------------------
# Connection / WAL
# ---------------------------------------------------------------------------


class TestConnectionSettings:
    def test_wal_mode_enabled(self, cache: IndexCache) -> None:
        cursor = cache.conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0] == "wal"

    def test_busy_timeout_set(self, cache: IndexCache) -> None:
        cursor = cache.conn.execute("PRAGMA busy_timeout")
        assert cursor.fetchone()[0] == 5000
