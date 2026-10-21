"""4.2 Documents & MinIO references. File bytes live in MinIO; these rows point to them."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import choices_check


class DocumentLifecycle(models.TextChoices):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    DELETED = "DELETED"


class Document(models.Model):
    Lifecycle = DocumentLifecycle

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.TextField()
    file_extension = models.CharField(max_length=20)
    mime_type = models.CharField(max_length=120)
    current_version = models.ForeignKey("DocumentVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    lifecycle_status = models.CharField(max_length=20, choices=Lifecycle.choices, default=Lifecycle.PENDING, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="documents", db_column="created_by"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "documents"
        ordering = ["-created_at"]
        constraints = [choices_check("lifecycle_status", DocumentLifecycle, "document_lifecycle_valid")]

    def __str__(self) -> str:
        return self.filename


class DocumentVersionStatus(models.TextChoices):
    UPLOADED = "UPLOADED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    INDEXING = "INDEXING"
    VALIDATING_INDEX = "VALIDATING_INDEX"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"
    DELETED = "DELETED"


class DocumentVersion(models.Model):
    Status = DocumentVersionStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    parent_version = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    content_sha256 = models.CharField(max_length=64, db_index=True)
    file_size = models.BigIntegerField()
    storage_bucket = models.CharField(max_length=63)
    storage_object_key = models.TextField()
    storage_version_id = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)

    class Meta:
        db_table = "document_versions"
        ordering = ["document", "-version_number"]
        constraints = [
            models.UniqueConstraint(fields=["document", "version_number"], name="document_version_unique"),
            models.CheckConstraint(condition=models.Q(version_number__gte=1), name="document_version_positive"),
            choices_check("status", DocumentVersionStatus, "document_version_status_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} v{self.version_number}"


class DocumentMetadata(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_version = models.OneToOneField(DocumentVersion, on_delete=models.CASCADE, related_name="metadata")
    metadata_json = models.JSONField(default=dict)

    class Meta:
        db_table = "document_metadata"
        verbose_name_plural = "document metadata"

    def __str__(self) -> str:
        return f"metadata of {self.document_version_id}"


class ArtifactType(models.TextChoices):
    DOCLING_JSON = "DOCLING_JSON"
    PAGE_TEXT = "PAGE_TEXT"
    OCR_TEXT = "OCR_TEXT"
    TABLE = "TABLE"
    IMAGE = "IMAGE"
    ORIGINAL = "ORIGINAL"
    EXPORT = "EXPORT"
    EMBEDDINGS = "EMBEDDINGS"


class ExtractedArtifact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_version = models.ForeignKey(DocumentVersion, on_delete=models.PROTECT, related_name="artifacts")
    artifact_type = models.CharField(max_length=20, choices=ArtifactType.choices)
    storage_bucket = models.CharField(max_length=63)
    storage_object_key = models.TextField()
    content_sha256 = models.CharField(max_length=64)
    metadata_json = models.JSONField(default=dict)

    class Meta:
        db_table = "extracted_artifacts"
        constraints = [choices_check("artifact_type", ArtifactType, "artifact_type_valid")]

    def __str__(self) -> str:
        return f"{self.artifact_type} of {self.document_version_id}"


class StorageObject(models.Model):
    """Optional shared registry of MinIO objects, so shared bytes are never deleted early."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bucket = models.CharField(max_length=63)
    object_key = models.TextField()
    object_version_id = models.CharField(max_length=100, null=True, blank=True)
    content_sha256 = models.CharField(max_length=64, db_index=True)
    size_bytes = models.BigIntegerField()
    object_type = models.CharField(max_length=20, choices=ArtifactType.choices)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "storage_objects"
        constraints = [
            models.UniqueConstraint(
                fields=["bucket", "object_key", "object_version_id"], nulls_distinct=False, name="storage_object_unique"
            ),
            choices_check("object_type", ArtifactType, "storage_object_type_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.bucket}/{self.object_key}"
