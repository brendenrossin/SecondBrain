"""Shared test fixtures."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from secondbrain.api.dependencies import get_settings
from secondbrain.main import app


@pytest.fixture
def client():
    return TestClient(app)


@contextmanager
def override_vault_path(path):
    """Temporarily override the cached settings vault_path, restoring it on exit."""
    settings = get_settings()
    original = settings.vault_path
    settings.vault_path = path
    try:
        yield settings
    finally:
        settings.vault_path = original


# --- Spec 001 recall fixture kit -------------------------------------------------


@pytest.fixture(scope="session")
def recall_index(tmp_path_factory):
    """Real stores over the committed fixture vault, built once per session (read-only)."""
    from tests.fixtures.recall.index import FIXTURE_VAULT, build_index

    return build_index(FIXTURE_VAULT, tmp_path_factory.mktemp("recall-index"))


@pytest.fixture
def recall_index_copy(recall_index, tmp_path):
    """A per-test copy of the session index for scenarios that write to stores."""
    from tests.fixtures.recall.index import copy_index

    return copy_index(recall_index, tmp_path / "recall-data")
