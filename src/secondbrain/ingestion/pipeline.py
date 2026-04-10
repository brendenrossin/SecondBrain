"""Ingestion pipeline orchestrator: fetch → audit → compile → write → index."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from secondbrain.ingestion.compiler import WikiCompiler, slugify_title
from secondbrain.ingestion.fetcher import FetchedContent
from secondbrain.ingestion.safety import SafetyAuditor


class JobStatus(StrEnum):
    PENDING = "pending"
    FETCHING = "fetching"
    AUDITING = "auditing"
    COMPILING = "compiling"
    INDEXING = "indexing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class IngestionJob:
    job_id: str
    url: str
    status: JobStatus = JobStatus.PENDING
    error: str = ""
    result_title: str = ""
    result_path: str = ""


class IngestionPipeline:
    """Orchestrates the full content ingestion flow.

    Steps:
    1. Fetch content from URL
    2. Audit for safety threats
    3. Check for existing duplicate page
    4. Compile into structured wiki markdown
    5. Write to wiki_dir
    6. Call index_callback if provided
    """

    def __init__(
        self,
        fetcher: Callable[[str], FetchedContent],
        auditor: SafetyAuditor,
        compiler: WikiCompiler,
        wiki_dir: Path,
        index_callback: Callable[[], None] | None = None,
        vault_manifest: str | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._auditor = auditor
        self._compiler = compiler
        self._wiki_dir = wiki_dir
        self._index_callback = index_callback
        self._vault_manifest = vault_manifest

    def run(self, url: str) -> IngestionJob:
        """Run the full ingestion pipeline synchronously.

        Returns an IngestionJob with the final status and result metadata.
        """
        job = IngestionJob(job_id=uuid.uuid4().hex[:12], url=url)

        try:
            # Step 1: Fetch
            job.status = JobStatus.FETCHING
            content = self._fetcher(url)

            # Step 2: Audit
            job.status = JobStatus.AUDITING
            audit_result = self._auditor.audit(content.raw_text, content.content_type)
            if not audit_result.is_safe:
                flags_str = ", ".join(audit_result.flags) if audit_result.flags else ""
                job.status = JobStatus.FAILED
                job.error = f"Content blocked by safety audit: {audit_result.reason}" + (
                    f" [flags: {flags_str}]" if flags_str else ""
                )
                return job

            # Step 3: Check for existing page with same source URL
            existing = self._compiler.find_existing_by_source(self._wiki_dir, url)

            # Step 4: Compile
            job.status = JobStatus.COMPILING
            markdown, title = self._compiler.compile(content, vault_manifest=self._vault_manifest)

            # Step 5: Write to disk (overwrite if duplicate found)
            if existing is not None:
                dest = existing
            else:
                slug = slugify_title(title) or "untitled"
                dest = self._wiki_dir / f"{slug}.md"
                if dest.exists():
                    counter = 1
                    while dest.exists():
                        dest = self._wiki_dir / f"{slug}-{counter}.md"
                        counter += 1

            dest.write_text(markdown, encoding="utf-8")

            # Step 6: Index callback
            if self._index_callback is not None:
                job.status = JobStatus.INDEXING
                self._index_callback()

            job.status = JobStatus.COMPLETE
            job.result_title = title
            job.result_path = str(dest)

        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)

        return job
