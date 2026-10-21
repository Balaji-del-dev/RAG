"""Retry and cancel processing jobs."""

from django.db import transaction
from django.utils import timezone

from apps.core import audit, outbox
from apps.core.exceptions import Conflict
from apps.documents.models import DocumentVersion

from .models import JobStatus, ProcessingJob


@transaction.atomic
def retry(job: ProcessingJob, *, by, request=None) -> ProcessingJob:
    if job.status != JobStatus.FAILED:
        raise Conflict("Only failed jobs can be retried.", code="job_not_failed")
    if job.document_version.status == DocumentVersion.Status.DELETED:
        raise Conflict("The document was deleted.", code="document_deleted")
    job.status, job.error_message, job.completed_at = JobStatus.QUEUED, None, None
    job.save(update_fields=["status", "error_message", "completed_at"])
    DocumentVersion.objects.filter(pk=job.document_version_id).update(status=DocumentVersion.Status.QUEUED)
    outbox.emit("job.dispatch", job, {"job_id": str(job.pk)})
    audit.record("job.retried", actor=by, entity_type="processing_job", entity_id=job.pk, request=request)
    return job


@transaction.atomic
def cancel(job: ProcessingJob, *, by, request=None) -> ProcessingJob:
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRY):
        raise Conflict("Only queued or running jobs can be cancelled.", code="job_not_running")
    job.status, job.completed_at = JobStatus.CANCELLED, timezone.now()
    job.save(update_fields=["status", "completed_at"])
    DocumentVersion.objects.filter(pk=job.document_version_id).exclude(status=DocumentVersion.Status.DELETED).update(
        status=DocumentVersion.Status.FAILED
    )
    audit.record("job.cancelled", actor=by, entity_type="processing_job", entity_id=job.pk, request=request)
    return job
