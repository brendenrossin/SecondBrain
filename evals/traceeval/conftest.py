"""Pytest fixtures for SecondBrain evals.

These evals call real LLM APIs — they require API keys and cost money.
"""

import os

import pytest

from secondbrain.indexing.context import ContextGenerator


@pytest.fixture
def context_generator():
    """Real ContextGenerator for behavioral evals.

    Requires ANTHROPIC_API_KEY environment variable.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    return ContextGenerator(api_key=api_key, model="claude-haiku-4-5")
