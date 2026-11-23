"""Spec 001 — Feature: embedder warmup and lazy load."""

import threading
import time
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pydantic import ValidationError

from secondbrain.config import Settings
from secondbrain.indexing.embedder import SentenceTransformerProvider


def _slow_model_factory(calls: list[str]):
    def factory(name):
        calls.append(name)
        time.sleep(0.2)
        model = MagicMock()
        model.encode.return_value = np.zeros((1, 4), dtype=np.float32)
        return model

    return factory


def test_concurrent_first_calls_load_the_model_once():
    """Scenario: concurrent first calls load the model once."""
    calls: list[str] = []
    provider = SentenceTransformerProvider("BAAI/bge-base-en-v1.5")
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        provider.embed_query("hello")

    with patch("sentence_transformers.SentenceTransformer", side_effect=_slow_model_factory(calls)):
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert calls == ["BAAI/bge-base-en-v1.5"]


def test_sanity_floor_cannot_go_below_the_retrievers_cut():
    """Scenario: the sanity floor cannot go below the retriever's cut."""
    with pytest.raises(ValidationError):
        Settings(recall_min_similarity=0.29)
    assert Settings(recall_min_similarity=0.3).recall_min_similarity == 0.3


def test_recall_settings_defaults():
    s = Settings(_env_file=None)
    assert s.recall_min_similarity == 0.40
    assert s.embedder_warmup is False


# --- Lifespan warmup --------------------------------------------------------------


@pytest.fixture
def lifespan_env(tmp_path):
    """Build (lifespan context, app, mock embedder, get_embedder mock) for given settings."""
    from secondbrain import main

    vector_store = MagicMock()

    with ExitStack() as stack:

        def make(**overrides):
            settings = Settings(_env_file=None, data_path=tmp_path, **overrides)
            embedder = MagicMock(model_name="mock")
            vector_store.reset_mock()
            stack.enter_context(patch.object(main, "get_settings", return_value=settings))
            stack.enter_context(patch.object(main, "init_tracing"))
            get_embedder = stack.enter_context(
                patch.object(main, "get_embedder", return_value=embedder)
            )
            # Never the live data/chroma from a test process.
            stack.enter_context(patch.object(main, "get_vector_store", return_value=vector_store))
            app = SimpleNamespace(state=SimpleNamespace())
            return main.lifespan(app), app, embedder, get_embedder

        yield make


async def test_warmup_off_by_default(lifespan_env):
    """Scenario: warmup off by default."""
    ctx, app, _embedder, get_embedder = lifespan_env()

    async with ctx:
        get_embedder.assert_not_called()
    assert not hasattr(app.state, "warmup_task")


async def test_warmup_skipped_for_non_local_embedder(lifespan_env):
    """Scenario: warmup is skipped for a non-local embedder."""
    ctx, app, _embedder, get_embedder = lifespan_env(
        embedder_warmup=True, embedding_provider="openai"
    )

    with patch("socket.socket.connect", side_effect=AssertionError("network call")) as connect:
        async with ctx:
            pass
    get_embedder.assert_not_called()
    connect.assert_not_called()
    assert not hasattr(app.state, "warmup_task")


async def test_warmup_runs_in_the_background(lifespan_env):
    """Scenario: warmup runs in the background."""
    ctx, app, embedder, _ = lifespan_env(embedder_warmup=True)
    release = threading.Event()
    embedder.embed_single.side_effect = lambda _text: release.wait(5)

    async with ctx:
        # The lifespan has yielded while embed_single is still blocked.
        assert not release.is_set()
        task = app.state.warmup_task
        assert not task.done()
        release.set()
        await task

    embedder.embed_single.assert_called_once_with("warmup")


async def test_warmup_failure_is_logged_not_raised(lifespan_env, caplog):
    """Scenario: warmup failure is logged, not raised."""
    ctx, app, embedder, _ = lifespan_env(embedder_warmup=True)
    embedder.embed_single.side_effect = RuntimeError("model load failed")

    with caplog.at_level("WARNING"):
        async with ctx:
            task = app.state.warmup_task  # captured inside: shutdown clears it (spec 004)
            await task

    assert task.exception() is None
    assert any(
        "warmup" in r.getMessage().lower() for r in caplog.records if r.levelname == "WARNING"
    )
    assert "Task exception was never retrieved" not in caplog.text


async def test_warmup_also_opens_the_vector_store(lifespan_env):
    """Fix C (tri-review): warmup opens Chroma too, so the first recall doesn't pay for it."""
    from secondbrain import main

    ctx, app, embedder, _ = lifespan_env(embedder_warmup=True)
    async with ctx:
        await app.state.warmup_task
    embedder.embed_single.assert_called_once_with("warmup")
    main.get_vector_store.return_value.count.assert_called_once_with()


# --- spec 004 Goal 7: warmup cancellation at shutdown ------------------------------------


async def test_a_still_running_warmup_task_is_cancelled_at_shutdown(lifespan_env, caplog, tmp_path):
    """Scenario: a still-running warmup task is cancelled at shutdown."""
    # A real vault path, so startup's own "vault missing" error doesn't count as noise.
    ctx, app, embedder, _ = lifespan_env(embedder_warmup=True, vault_path=tmp_path)
    release = threading.Event()
    embedder.embed_single.side_effect = lambda _text: release.wait(5)

    try:
        with caplog.at_level("WARNING"):
            async with ctx:
                task = app.state.warmup_task
                assert not task.done()
    finally:
        release.set()  # no worker thread outlives the test

    assert task.cancelled() is True
    assert app.state.warmup_task is None
    assert [r for r in caplog.records if r.levelno >= 30] == []


async def test_a_finished_warmup_is_not_cancelled_at_shutdown(lifespan_env):
    """Scenario: a finished warmup is not cancelled at shutdown."""
    ctx, app, _embedder, _ = lifespan_env(embedder_warmup=True)

    async with ctx:
        task = app.state.warmup_task
        await task
        spy = MagicMock(wraps=task)
        app.state.warmup_task = spy

    assert task.cancelled() is False and task.exception() is None
    spy.cancel.assert_not_called()
    assert app.state.warmup_task is None


async def test_shutdown_with_warmup_disabled_is_a_no_op(lifespan_env):
    """Scenario: shutdown with warmup disabled is a no-op."""
    ctx, app, _embedder, _ = lifespan_env(embedder_warmup=False)

    async with ctx:
        pass  # exiting raises nothing

    assert not hasattr(app.state, "warmup_task")
