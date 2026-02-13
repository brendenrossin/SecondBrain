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
