"""Wiki ingestion and answer-save endpoints (KLIB-1 / KLIB-3)."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException

from secondbrain.api.dependencies import (
    get_safety_auditor,
    get_settings,
    get_vault_manifest,
    get_wiki_compiler,
)
from secondbrain.ingestion.fetcher import detect_content_type
from secondbrain.ingestion.pipeline import IngestionJob, IngestionPipeline, JobStatus
from secondbrain.models import (
    WikiIngestRequest,
    WikiIngestResponse,
    WikiJobStatusResponse,
    WikiSaveRequest,
    WikiSaveResponse,
    WikiSuggestion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["wiki"])

# In-memory job tracker (process-local; jobs are ephemeral)
_jobs: dict[str, IngestionJob] = {}

_FACTUAL_PREFIXES = ("when ", "where ", "who ")
_MIN_ANSWER_CHARS = 200
_MIN_FACTUAL_CHARS = 500
_MIN_CITATION_COUNT = 3


def compute_wiki_suggestion(
    retrieval_label: str,
    answer_text: str,
    citation_note_titles: list[str],
    query: str,
) -> WikiSuggestion:
    """Determine whether an answer is worth saving as a wiki page.

    Returns WikiSuggestion(eligible=False) with a reason string when ineligible,
    or WikiSuggestion(eligible=True) with a reason when eligible.
    """
    if retrieval_label != "PASS":
        return WikiSuggestion(eligible=False, reason="Retrieval did not pass quality check")

    unique_titles = len(set(citation_note_titles))
    if unique_titles < _MIN_CITATION_COUNT:
        return WikiSuggestion(eligible=False, reason="Too few distinct citation sources")

    if len(answer_text) < _MIN_ANSWER_CHARS:
        return WikiSuggestion(eligible=False, reason="Answer too short to be a useful wiki page")

    # Heuristic: short factual lookups ("when/where/who ...") need a longer answer
    query_lower = query.lower().strip()
    if (
        any(query_lower.startswith(prefix) for prefix in _FACTUAL_PREFIXES)
        and len(answer_text) < _MIN_FACTUAL_CHARS
    ):
        return WikiSuggestion(
            eligible=False, reason="Factual lookup answer too brief for a wiki page"
        )

    return WikiSuggestion(
        eligible=True,
        reason=f"Synthesizes {unique_titles} sources into comprehensive overview",
    )


def _start_ingestion_job(url: str) -> str:
    """Create and launch an ingestion job; return the job_id."""
    from secondbrain.ingestion.fetcher import fetch_content

    settings = get_settings()

    if not settings.vault_path:
        raise HTTPException(status_code=500, detail="SECONDBRAIN_VAULT_PATH not configured")

    wiki_dir = settings.vault_path / "Wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    pipeline = IngestionPipeline(
        fetcher=fetch_content,
        auditor=get_safety_auditor(),
        compiler=get_wiki_compiler(),
        wiki_dir=wiki_dir,
        vault_manifest=get_vault_manifest(),
    )

    job_id = uuid.uuid4().hex[:12]
    job = IngestionJob(job_id=job_id, url=url, status=JobStatus.FETCHING)
    _jobs[job_id] = job

    async def _run() -> None:
        result = await asyncio.to_thread(pipeline.run, url)
        # Merge result fields back into the tracked job
        job.status = result.status
        job.error = result.error
        job.result_title = result.result_title
        job.result_path = result.result_path

    asyncio.create_task(_run())
    return job_id


@router.post("/wiki/ingest", response_model=WikiIngestResponse)
async def wiki_ingest(request: WikiIngestRequest) -> WikiIngestResponse:
    """Start a background ingestion job for a URL.

    Validates URL scheme/type synchronously, then returns immediately with a
    job_id that can be polled via GET /api/v1/wiki/ingest/{job_id}.
    """
    try:
        detect_content_type(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        job_id = _start_ingestion_job(request.url)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to start ingestion job for %s", request.url)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return WikiIngestResponse(
        job_id=job_id,
        status="fetching",
        message="Ingestion started",
    )


@router.get("/wiki/ingest/{job_id}", response_model=WikiJobStatusResponse)
async def wiki_ingest_status(job_id: str) -> WikiJobStatusResponse:
    """Poll the status of an ingestion job."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    return WikiJobStatusResponse(
        job_id=job.job_id,
        status=str(job.status),
        error=job.error,
        result_title=job.result_title,
        result_path=job.result_path,
    )


@router.post("/wiki/save", response_model=WikiSaveResponse)
async def wiki_save(request: WikiSaveRequest) -> WikiSaveResponse:
    """Compile a chat answer into a wiki page and write it to the vault.

    Uses WikiCompiler.compile_answer to restructure the answer into a
    reference-quality Obsidian note in the Wiki/ folder.
    """
    settings = get_settings()
    if not settings.vault_path:
        raise HTTPException(status_code=500, detail="SECONDBRAIN_VAULT_PATH not configured")

    wiki_dir = settings.vault_path / "Wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    compiler = get_wiki_compiler()

    try:
        markdown, title = await asyncio.to_thread(
            compiler.compile_answer,
            request.answer_text,
            request.query,
            request.citations,
        )
    except Exception as exc:
        logger.exception("Wiki compile_answer failed for query %r", request.query)
        raise HTTPException(status_code=500, detail=f"Compilation failed: {exc}") from exc

    from secondbrain.ingestion.compiler import slugify_title

    slug = slugify_title(title) or "untitled"
    dest = wiki_dir / f"{slug}.md"
    if dest.exists():
        counter = 1
        while dest.exists():
            dest = wiki_dir / f"{slug}-{counter}.md"
            counter += 1

    dest.write_text(markdown, encoding="utf-8")
    logger.info("Saved wiki answer to %s (%d chars)", dest, len(markdown))

    return WikiSaveResponse(
        title=title,
        path=str(dest),
        message=f"Saved to Wiki/{dest.name}",
    )
