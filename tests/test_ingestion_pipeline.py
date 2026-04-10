"""Tests for the IngestionPipeline module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from secondbrain.ingestion.fetcher import ContentType, FetchedContent
from secondbrain.ingestion.pipeline import IngestionJob, IngestionPipeline, JobStatus
from secondbrain.ingestion.safety import AuditResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fetched_content(
    url: str = "https://example.com/article",
    title: str = "Test Article",
) -> FetchedContent:
    return FetchedContent(
        source_url=url,
        title=title,
        content_type=ContentType.WEB_ARTICLE,
        raw_text="Some article content.",
    )


def _make_pipeline(
    tmp_path: Path,
    fetched_content: FetchedContent | None = None,
    is_safe: bool = True,
    index_callback=None,
    vault_manifest: str | None = None,
) -> tuple[IngestionPipeline, MagicMock, MagicMock, MagicMock]:
    if fetched_content is None:
        fetched_content = _make_fetched_content()

    mock_fetcher = MagicMock(return_value=fetched_content)

    mock_auditor = MagicMock()
    mock_auditor.audit.return_value = AuditResult(
        is_safe=is_safe,
        reason="Clean." if is_safe else "Prompt injection detected.",
        flags=[] if is_safe else ["prompt_injection"],
    )

    mock_compiler = MagicMock()
    mock_compiler.compile.return_value = (
        "---\ntitle: Test Article\n---\n\n## Content\n\nBody text.",
        "Test Article",
    )
    mock_compiler.find_existing_by_source.return_value = None

    pipeline = IngestionPipeline(
        fetcher=mock_fetcher,
        auditor=mock_auditor,
        compiler=mock_compiler,
        wiki_dir=tmp_path,
        index_callback=index_callback,
        vault_manifest=vault_manifest,
    )
    return pipeline, mock_fetcher, mock_auditor, mock_compiler


# ---------------------------------------------------------------------------
# JobStatus
# ---------------------------------------------------------------------------


class TestJobStatus:
    def test_status_values_are_strings(self) -> None:
        for status in JobStatus:
            assert isinstance(status, str)

    def test_status_progression(self) -> None:
        statuses = list(JobStatus)
        assert JobStatus.PENDING in statuses
        assert JobStatus.FETCHING in statuses
        assert JobStatus.AUDITING in statuses
        assert JobStatus.COMPILING in statuses
        assert JobStatus.INDEXING in statuses
        assert JobStatus.COMPLETE in statuses
        assert JobStatus.FAILED in statuses

    def test_status_str_values(self) -> None:
        assert JobStatus.PENDING == "pending"
        assert JobStatus.FETCHING == "fetching"
        assert JobStatus.AUDITING == "auditing"
        assert JobStatus.COMPILING == "compiling"
        assert JobStatus.INDEXING == "indexing"
        assert JobStatus.COMPLETE == "complete"
        assert JobStatus.FAILED == "failed"


# ---------------------------------------------------------------------------
# IngestionJob
# ---------------------------------------------------------------------------


class TestIngestionJob:
    def test_defaults(self) -> None:
        job = IngestionJob(job_id="abc123", url="https://example.com")
        assert job.status == JobStatus.PENDING
        assert job.error == ""
        assert job.result_title == ""
        assert job.result_path == ""

    def test_fields_set_correctly(self) -> None:
        job = IngestionJob(
            job_id="xyz",
            url="https://example.com",
            status=JobStatus.COMPLETE,
            result_title="My Article",
            result_path="/vault/wiki/my-article.md",
        )
        assert job.job_id == "xyz"
        assert job.url == "https://example.com"
        assert job.status == JobStatus.COMPLETE
        assert job.result_title == "My Article"
        assert job.result_path == "/vault/wiki/my-article.md"


# ---------------------------------------------------------------------------
# IngestionPipeline.run — success path
# ---------------------------------------------------------------------------


class TestIngestionPipeline:
    def test_run_pipeline_success(self, tmp_path: Path) -> None:
        pipeline, mock_fetcher, mock_auditor, mock_compiler = _make_pipeline(tmp_path)

        job = pipeline.run("https://example.com/article")

        assert job.status == JobStatus.COMPLETE
        assert job.result_title == "Test Article"
        assert job.result_path != ""
        assert Path(job.result_path).exists()

    def test_run_pipeline_writes_file_to_wiki_dir(self, tmp_path: Path) -> None:
        pipeline, _, _, _ = _make_pipeline(tmp_path)

        pipeline.run("https://example.com/article")

        written_files = list(tmp_path.glob("*.md"))
        assert len(written_files) == 1
        content = written_files[0].read_text(encoding="utf-8")
        assert "## Content" in content

    def test_run_pipeline_job_id_is_12_char_hex(self, tmp_path: Path) -> None:
        pipeline, _, _, _ = _make_pipeline(tmp_path)

        job = pipeline.run("https://example.com/article")

        assert len(job.job_id) == 12
        # Should be valid hex
        int(job.job_id, 16)

    def test_run_pipeline_calls_fetcher_with_url(self, tmp_path: Path) -> None:
        pipeline, mock_fetcher, _, _ = _make_pipeline(tmp_path)
        url = "https://example.com/article"

        pipeline.run(url)

        mock_fetcher.assert_called_once_with(url)

    def test_run_pipeline_calls_auditor_with_raw_text_and_content_type(
        self, tmp_path: Path
    ) -> None:
        fetched = _make_fetched_content()
        pipeline, _, mock_auditor, _ = _make_pipeline(tmp_path, fetched_content=fetched)

        pipeline.run("https://example.com/article")

        mock_auditor.audit.assert_called_once_with(fetched.raw_text, fetched.content_type)

    def test_run_pipeline_calls_compiler_compile(self, tmp_path: Path) -> None:
        pipeline, _, _, mock_compiler = _make_pipeline(tmp_path)

        pipeline.run("https://example.com/article")

        mock_compiler.compile.assert_called_once()

    def test_run_pipeline_passes_vault_manifest_to_compiler(self, tmp_path: Path) -> None:
        pipeline, _, _, mock_compiler = _make_pipeline(tmp_path, vault_manifest="topic: Python, AI")

        pipeline.run("https://example.com/article")

        call_kwargs = mock_compiler.compile.call_args
        assert call_kwargs.kwargs.get("vault_manifest") == "topic: Python, AI"

    def test_run_pipeline_checks_for_duplicate(self, tmp_path: Path) -> None:
        pipeline, _, _, mock_compiler = _make_pipeline(tmp_path)
        url = "https://example.com/article"

        pipeline.run(url)

        mock_compiler.find_existing_by_source.assert_called_once_with(tmp_path, url)

    def test_run_pipeline_overwrites_existing_file(self, tmp_path: Path) -> None:
        existing = tmp_path / "old-slug.md"
        existing.write_text("old content", encoding="utf-8")

        pipeline, _, _, mock_compiler = _make_pipeline(tmp_path)
        mock_compiler.find_existing_by_source.return_value = existing

        job = pipeline.run("https://example.com/article")

        # Pipeline should still complete successfully
        assert job.status == JobStatus.COMPLETE

    def test_run_pipeline_slug_filename_from_title(self, tmp_path: Path) -> None:
        fetched = _make_fetched_content(title="My Cool Article")
        pipeline, _, _, mock_compiler = _make_pipeline(tmp_path, fetched_content=fetched)
        mock_compiler.compile.return_value = (
            "---\ntitle: My Cool Article\n---\n\nContent.",
            "My Cool Article",
        )

        pipeline.run("https://example.com/article")

        written_files = list(tmp_path.glob("*.md"))
        assert len(written_files) == 1
        assert written_files[0].name == "my-cool-article.md"

    def test_run_pipeline_handles_filename_collision_with_counter(self, tmp_path: Path) -> None:
        # Pre-create the slug file to force a collision
        (tmp_path / "test-article.md").write_text("existing", encoding="utf-8")

        pipeline, _, _, mock_compiler = _make_pipeline(tmp_path)
        mock_compiler.compile.return_value = (
            "---\ntitle: Test Article\n---\n\nContent.",
            "Test Article",
        )

        job = pipeline.run("https://example.com/article")

        assert job.status == JobStatus.COMPLETE
        # Should have created test-article-1.md or similar
        written_files = list(tmp_path.glob("*.md"))
        names = [f.name for f in written_files]
        assert any("-1" in name for name in names) or len(written_files) == 2

    # -------------------------------------------------------------------------
    # Safety blocked
    # -------------------------------------------------------------------------

    def test_run_pipeline_safety_blocked(self, tmp_path: Path) -> None:
        pipeline, _, mock_auditor, mock_compiler = _make_pipeline(tmp_path, is_safe=False)

        job = pipeline.run("https://example.com/bad-content")

        assert job.status == JobStatus.FAILED
        assert "blocked" in job.error.lower()

    def test_run_pipeline_safety_blocked_error_includes_reason(self, tmp_path: Path) -> None:
        pipeline, _, mock_auditor, _ = _make_pipeline(tmp_path, is_safe=False)
        mock_auditor.audit.return_value = AuditResult(
            is_safe=False,
            reason="Contains jailbreak attempt.",
            flags=["jailbreak"],
        )

        job = pipeline.run("https://example.com/bad")

        assert "jailbreak" in job.error.lower() or "Contains jailbreak" in job.error

    def test_run_pipeline_safety_blocked_compiler_never_called(self, tmp_path: Path) -> None:
        pipeline, _, _, mock_compiler = _make_pipeline(tmp_path, is_safe=False)

        pipeline.run("https://example.com/bad")

        mock_compiler.compile.assert_not_called()

    def test_run_pipeline_safety_blocked_no_file_written(self, tmp_path: Path) -> None:
        pipeline, _, _, _ = _make_pipeline(tmp_path, is_safe=False)

        pipeline.run("https://example.com/bad")

        assert list(tmp_path.glob("*.md")) == []

    # -------------------------------------------------------------------------
    # Fetch failure
    # -------------------------------------------------------------------------

    def test_run_pipeline_fetch_failure(self, tmp_path: Path) -> None:
        mock_fetcher = MagicMock(side_effect=ValueError("Connection refused"))
        mock_auditor = MagicMock()
        mock_compiler = MagicMock()
        mock_compiler.find_existing_by_source.return_value = None

        pipeline = IngestionPipeline(
            fetcher=mock_fetcher,
            auditor=mock_auditor,
            compiler=mock_compiler,
            wiki_dir=tmp_path,
        )

        job = pipeline.run("https://example.com/unreachable")

        assert job.status == JobStatus.FAILED
        assert "Connection refused" in job.error

    def test_run_pipeline_fetch_failure_auditor_never_called(self, tmp_path: Path) -> None:
        mock_fetcher = MagicMock(side_effect=RuntimeError("Timeout"))
        mock_auditor = MagicMock()
        mock_compiler = MagicMock()
        mock_compiler.find_existing_by_source.return_value = None

        pipeline = IngestionPipeline(
            fetcher=mock_fetcher,
            auditor=mock_auditor,
            compiler=mock_compiler,
            wiki_dir=tmp_path,
        )

        pipeline.run("https://example.com/unreachable")

        mock_auditor.audit.assert_not_called()

    # -------------------------------------------------------------------------
    # Index callback
    # -------------------------------------------------------------------------

    def test_run_pipeline_calls_index_callback(self, tmp_path: Path) -> None:
        mock_callback = MagicMock()
        pipeline, _, _, _ = _make_pipeline(tmp_path, index_callback=mock_callback)

        pipeline.run("https://example.com/article")

        mock_callback.assert_called_once()

    def test_run_pipeline_no_index_callback_succeeds(self, tmp_path: Path) -> None:
        pipeline, _, _, _ = _make_pipeline(tmp_path, index_callback=None)

        job = pipeline.run("https://example.com/article")

        assert job.status == JobStatus.COMPLETE

    def test_run_pipeline_index_callback_not_called_on_failure(self, tmp_path: Path) -> None:
        mock_callback = MagicMock()
        pipeline, _, _, _ = _make_pipeline(tmp_path, is_safe=False, index_callback=mock_callback)

        pipeline.run("https://example.com/bad")

        mock_callback.assert_not_called()

    def test_run_pipeline_compiler_failure_captured(self, tmp_path: Path) -> None:
        pipeline, _, _, mock_compiler = _make_pipeline(tmp_path)
        mock_compiler.compile.side_effect = RuntimeError("LLM timeout")

        job = pipeline.run("https://example.com/article")

        assert job.status == JobStatus.FAILED
        assert "LLM timeout" in job.error
