"""Upload, new version, delete, access change. Bytes go to MinIO first; then one transaction writes the rows."""

import os
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import AccessGroup, DocumentAccessGrant
from apps.accounts.selectors import access_scope
from apps.core import audit, outbox
from apps.core.clients import storage
from apps.core.exceptions import Conflict
from apps.processing.models import JobStatus, ProcessingJob
from apps.registry.services import live_version

from .models import Document, DocumentVersion
from .validation import CheckedFile, check_upload


def assignable_groups(user):
    """Groups a user may share a document with: their own groups, or every group for Admins."""
    if user.has_perm("accounts.manage"):
        return AccessGroup.objects.all()
    return AccessGroup.objects.filter(name__in=access_scope(user))


def resolve_groups(user, group_ids) -> list[AccessGroup]:
    ids = {str(g) for g in group_ids or []}
    if not ids:
        raise ValidationError({"access_group_ids": ["Choose at least one access group."]})
    groups = list(assignable_groups(user).filter(pk__in=ids))
    if len(groups) != len(ids):
        raise ValidationError({"access_group_ids": ["You can only share with groups you belong to."]})
    return groups


def visible_duplicate(user, sha256: str) -> Document | None:
    from .selectors import visible_documents

    return visible_documents(user).filter(versions__content_sha256=sha256).distinct().first()


def _object_key(document_id: uuid.UUID, version_number: int, checked: CheckedFile) -> str:
    return f"documents/{document_id}/v{version_number}/{checked.sha256}.{checked.extension}"


def _require_live_pipeline():
    version = live_version()
    if version is None:
        raise Conflict(
            "No pipeline is published yet. A Release approver must publish the first pipeline version.", code="no_live_pipeline"
        )
    return version


def _queue_job(version: DocumentVersion, pipeline_version, job_type=ProcessingJob.JobType.INGEST) -> ProcessingJob:
    job = ProcessingJob.objects.create(
        document_version=version, pipeline_version=pipeline_version, job_type=job_type, status=JobStatus.QUEUED
    )
    outbox.emit("job.dispatch", job, {"job_id": str(job.pk)})
    return job


def upload_document(*, user, uploaded, access_group_ids, request=None) -> tuple[Document, bool]:
    """Returns (document, duplicate). A duplicate the user can see is returned instead of a new upload."""
    groups = resolve_groups(user, access_group_ids)
    checked = check_upload(uploaded)
    try:
        duplicate = visible_duplicate(user, checked.sha256)
        if duplicate is not None:
            return duplicate, True
        pipeline_version = _require_live_pipeline()
        document_id = uuid.uuid4()
        key = _object_key(document_id, 1, checked)
        object_version = storage.put_file(settings.S3_BUCKET_ORIGINALS, key, checked.path, checked.mime_type)
        with transaction.atomic():
            document = Document.objects.create(
                id=document_id,
                filename=checked.filename,
                file_extension=checked.extension,
                mime_type=checked.mime_type,
                created_by=user,
            )
            version = DocumentVersion.objects.create(
                document=document,
                version_number=1,
                content_sha256=checked.sha256,
                file_size=checked.size,
                storage_bucket=settings.S3_BUCKET_ORIGINALS,
                storage_object_key=key,
                storage_version_id=object_version,
                status=DocumentVersion.Status.QUEUED,
            )
            document.current_version = version
            document.save(update_fields=["current_version"])
            DocumentAccessGrant.objects.bulk_create(
                DocumentAccessGrant(document=document, access_group=g, granted_by=user) for g in groups
            )
            job = _queue_job(version, pipeline_version)
            audit.record(
                "document.uploaded", actor=user, entity_type="document", entity_id=document.pk, request=request,
                details={"filename": checked.filename, "size": checked.size, "sha256": checked.sha256,
                         "access_groups": sorted(g.name for g in groups), "job_id": str(job.pk)},
            )  # fmt: skip
        return document, False
    finally:
        os.unlink(checked.path)


def upload_new_version(*, user, document: Document, uploaded, request=None) -> DocumentVersion:
    if document.deleted_at is not None:
        raise Conflict("This document was deleted.", code="document_deleted")
    checked = check_upload(uploaded)
    try:
        if checked.extension != document.file_extension:
            raise ValidationError({"file": [f"A new version must also be a .{document.file_extension} file."]})
        if document.versions.filter(content_sha256=checked.sha256).exists():
            raise Conflict("This exact file is already a version of this document.", code="duplicate_document")
        pipeline_version = _require_live_pipeline()
        current = document.current_version
        number = (document.versions.order_by("-version_number").values_list("version_number", flat=True).first() or 0) + 1
        key = _object_key(document.pk, number, checked)
        object_version = storage.put_file(settings.S3_BUCKET_ORIGINALS, key, checked.path, checked.mime_type)
        with transaction.atomic():
            version = DocumentVersion.objects.create(
                document=document,
                version_number=number,
                parent_version=current,
                content_sha256=checked.sha256,
                file_size=checked.size,
                storage_bucket=settings.S3_BUCKET_ORIGINALS,
                storage_object_key=key,
                storage_version_id=object_version,
                status=DocumentVersion.Status.QUEUED,
            )
            job = _queue_job(version, pipeline_version)
            audit.record(
                "document.version_uploaded", actor=user, entity_type="document", entity_id=document.pk, request=request,
                details={"version_number": number, "sha256": checked.sha256, "job_id": str(job.pk)},
            )  # fmt: skip
        return version
    finally:
        os.unlink(checked.path)


@transaction.atomic
def delete_document(*, user, document: Document, request=None) -> None:
    """Soft delete: hidden at once, removed from both indexes by the index.delete task."""
    if document.deleted_at is not None:
        return
    now = timezone.now()
    document.deleted_at = now
    document.lifecycle_status = Document.Lifecycle.DELETED
    document.save(update_fields=["deleted_at", "lifecycle_status", "updated_at"])
    for version in document.versions.exclude(status=DocumentVersion.Status.DELETED):
        version.status = DocumentVersion.Status.DELETED
        version.save(update_fields=["status"])
        outbox.emit("index.delete", version, {"document_version_id": str(version.pk), "purge_files": True})
    ProcessingJob.objects.filter(document_version__document=document, status__in=[JobStatus.QUEUED, JobStatus.RETRY]).update(
        status=JobStatus.CANCELLED, completed_at=now
    )
    audit.record("document.deleted", actor=user, entity_type="document", entity_id=document.pk, request=request,
                 details={"filename": document.filename})  # fmt: skip


@transaction.atomic
def set_access_groups(*, user, document: Document, access_group_ids, request=None) -> list[str]:
    groups = resolve_groups(user, access_group_ids)
    DocumentAccessGrant.objects.filter(document=document).exclude(access_group__in=groups).delete()
    have = set(document.access_grants.values_list("access_group_id", flat=True))
    DocumentAccessGrant.objects.bulk_create(
        DocumentAccessGrant(document=document, access_group=g, granted_by=user) for g in groups if g.pk not in have
    )
    names = sorted(g.name for g in groups)
    outbox.emit("index.acl", document, {"document_id": str(document.pk)})
    audit.record("document.access_changed", actor=user, entity_type="document", entity_id=document.pk, request=request,
                 details={"access_groups": names})  # fmt: skip
    return names
