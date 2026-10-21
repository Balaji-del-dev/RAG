"""Run one processing job: every enabled step in order, each recorded as a processing_step_runs row."""

import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import structlog
from django.db import transaction
from django.utils import timezone

from apps.core import outbox
from apps.documents.models import Document, DocumentVersion

from .components import chunking, parse, store, text
from .components.base import ContentError, Context, TransientError
from .models import JobStatus, ProcessingJob, ProcessingStepRun

log = structlog.get_logger(__name__)

IMPLEMENTATIONS: dict[str, Callable[[Context, dict], dict]] = {
    "read.minio_original": parse.read_original,
    "parse.docling": parse.parse_docling,
    "parse.pymupdf": parse.parse_pymupdf,
    "parse.plain": parse.parse_plain,
    "ocr.tesseract": parse.ocr_tesseract,
    "ocr.easyocr": parse.ocr_easyocr,
    "clean.normalize": text.clean_normalize,
    "structure.rebuild": text.structure_rebuild,
    "enrich.none": text.enrich_none,
    "chunk.structure_aware": chunking.chunk_structure_aware,
    "chunk.quality_checks": chunking.chunk_quality_checks,
    "chunk.persist": store.chunk_persist,
    "embed.sentence_transformers": store.embed_sentence_transformers,
}

FINISHED = {JobStatus.SUCCEEDED, JobStatus.CANCELLED}


def _set_version_status(version: DocumentVersion, status: str) -> None:
    DocumentVersion.objects.filter(pk=version.pk).exclude(status=DocumentVersion.Status.DELETED).update(status=status)


def _fail(job: ProcessingJob, message: str) -> None:
    with transaction.atomic():
        ProcessingJob.objects.filter(pk=job.pk).update(
            status=JobStatus.FAILED, error_message=message[:2000], completed_at=timezone.now()
        )
        version = job.document_version
        _set_version_status(version, DocumentVersion.Status.FAILED)
        document = version.document
        if not document.versions.filter(status=DocumentVersion.Status.PUBLISHED).exists():
            Document.objects.filter(pk=document.pk, deleted_at__isnull=True).update(lifecycle_status=Document.Lifecycle.FAILED)


def run(job_id: str) -> str:
    job = ProcessingJob.objects.select_related("document_version__document", "pipeline_version").get(pk=job_id)
    if job.status in FINISHED or job.document_version.status == DocumentVersion.Status.DELETED:
        return job.status
    ProcessingJob.objects.filter(pk=job.pk).update(
        status=JobStatus.RUNNING, attempt_count=job.attempt_count + 1, started_at=timezone.now(), error_message=None
    )
    attempt = job.attempt_count + 1
    _set_version_status(job.document_version, DocumentVersion.Status.PROCESSING)
    steps = list(job.pipeline_version.steps.filter(is_enabled=True).select_related("component").order_by("step_order"))
    log.info("processing.started", job_id=str(job.pk), attempt=attempt, steps=len(steps))

    with tempfile.TemporaryDirectory(prefix="rag-job-") as workdir:
        ctx = Context(job=job, version=job.document_version, pipeline_version=job.pipeline_version, workdir=Path(workdir))
        for step in steps:
            if ProcessingJob.objects.filter(pk=job.pk, status=JobStatus.CANCELLED).exists():
                log.info("processing.cancelled", job_id=str(job.pk))
                return JobStatus.CANCELLED
            key = step.component.name
            row = ProcessingStepRun.objects.create(
                processing_job=job,
                step_name=key,
                input_summary={"step_order": step.step_order, "attempt": attempt, "config": step.config_json},
            )
            started = time.monotonic()
            try:
                summary = IMPLEMENTATIONS[key](ctx, step.config_json)
            except ContentError as exc:
                _close_step(row, ProcessingStepRun.Status.FAILED, started, error=str(exc))
                _fail(job, f"{key}: {exc}")
                log.warning("processing.content_error", job_id=str(job.pk), step=key, error=str(exc))
                return JobStatus.FAILED
            except TransientError as exc:
                _close_step(row, ProcessingStepRun.Status.FAILED, started, error=str(exc))
                ProcessingJob.objects.filter(pk=job.pk).update(status=JobStatus.RETRY, error_message=f"{key}: {exc}"[:2000])
                raise
            except Exception as exc:
                log.exception("processing.step_crashed", job_id=str(job.pk), step=key)
                _close_step(row, ProcessingStepRun.Status.FAILED, started, error=f"{type(exc).__name__}: {exc}")
                _fail(job, f"{key}: unexpected error ({type(exc).__name__}: {exc})")
                return JobStatus.FAILED
            status = ProcessingStepRun.Status.SKIPPED if summary.get("skipped") else ProcessingStepRun.Status.SUCCEEDED
            _close_step(row, status, started, output=summary)

    with transaction.atomic():
        ProcessingJob.objects.filter(pk=job.pk).update(
            status=JobStatus.SUCCEEDED, completed_at=timezone.now(), error_message=None
        )
        _set_version_status(job.document_version, DocumentVersion.Status.INDEXING)
        outbox.emit(
            "index.upsert",
            job.document_version,
            {"document_version_id": str(job.document_version_id), "pipeline_version_id": str(job.pipeline_version_id)},
        )
    log.info("processing.succeeded", job_id=str(job.pk), chunks=len(ctx.chunks))
    return JobStatus.SUCCEEDED


def _close_step(
    row: ProcessingStepRun, status: str, started: float, *, output: dict | None = None, error: str | None = None
) -> None:
    row.status = status
    row.duration_ms = int((time.monotonic() - started) * 1000)
    row.output_summary = output
    row.error_message = error[:2000] if error else None
    row.save(update_fields=["status", "duration_ms", "output_summary", "error_message"])


def give_up(job_id: str, exc: Exception) -> None:
    job = ProcessingJob.objects.select_related("document_version__document").filter(pk=job_id).first()
    if job is not None and job.status not in FINISHED and job.status != JobStatus.FAILED:
        _fail(job, f"gave up after retries: {exc}")
