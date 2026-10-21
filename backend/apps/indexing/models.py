"""4.4 Index lifecycle. One generation names a Qdrant collection and an OpenSearch index together."""

import uuid

from django.db import models

from apps.core.models import choices_check
from apps.processing.models import JobStatus


class IndexGenerationStatus(models.TextChoices):
    BUILDING = "BUILDING"
    VALIDATING = "VALIDATING"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


class IndexGeneration(models.Model):
    Status = IndexGenerationStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline_version = models.ForeignKey("registry.PipelineVersion", on_delete=models.PROTECT, related_name="index_generations")
    generation_number = models.PositiveIntegerField()
    qdrant_collection = models.CharField(max_length=255)
    opensearch_index = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BUILDING)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "index_generations"
        ordering = ["-generation_number"]
        constraints = [
            models.UniqueConstraint(fields=["pipeline_version", "generation_number"], name="index_generation_unique"),
            # PostgreSQL decides which generation is live: at most one row is PUBLISHED.
            models.UniqueConstraint(fields=["status"], condition=models.Q(status="PUBLISHED"), name="one_published_generation"),
            choices_check("status", IndexGenerationStatus, "index_generation_status_valid"),
        ]

    def __str__(self) -> str:
        return f"generation {self.generation_number} ({self.status})"


class IndexBuildJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    index_generation = models.ForeignKey(IndexGeneration, on_delete=models.PROTECT, related_name="build_jobs")
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.QUEUED)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "index_build_jobs"
        constraints = [choices_check("status", JobStatus, "index_build_job_status_valid")]

    def __str__(self) -> str:
        return f"build of {self.index_generation_id} ({self.status})"


class IndexMembershipStatus(models.TextChoices):
    PENDING = "PENDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"
    RETRY = "RETRY"
    REMOVED = "REMOVED"


class IndexMembership(models.Model):
    Status = IndexMembershipStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    index_generation = models.ForeignKey(IndexGeneration, on_delete=models.PROTECT, related_name="memberships")
    document_version = models.ForeignKey("documents.DocumentVersion", on_delete=models.PROTECT, related_name="index_memberships")
    chunk = models.ForeignKey("processing.Chunk", on_delete=models.PROTECT, related_name="index_memberships")
    qdrant_point_id = models.UUIDField()
    opensearch_document_id = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        db_table = "index_memberships"
        indexes = [models.Index(fields=["index_generation", "document_version"], name="index_membership_version_idx")]
        constraints = [
            models.UniqueConstraint(fields=["index_generation", "chunk"], name="index_membership_unique"),
            choices_check("status", IndexMembershipStatus, "index_membership_status_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.chunk_id} in {self.index_generation_id} ({self.status})"


class IndexValidationStatus(models.TextChoices):
    PASSED = "PASSED"
    FAILED = "FAILED"


class IndexValidationType(models.TextChoices):
    COUNT = "COUNT"
    MISSING = "MISSING"
    DUPLICATE = "DUPLICATE"
    ORPHAN = "ORPHAN"
    SMOKE_DENSE = "SMOKE_DENSE"
    SMOKE_LEXICAL = "SMOKE_LEXICAL"
    SMOKE_HYBRID = "SMOKE_HYBRID"


class IndexValidation(models.Model):
    Type = IndexValidationType

    Status = IndexValidationStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    index_generation = models.ForeignKey(IndexGeneration, on_delete=models.CASCADE, related_name="validations")
    validation_type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    expected_count = models.PositiveIntegerField(null=True, blank=True)
    actual_count = models.PositiveIntegerField(null=True, blank=True)
    details_json = models.JSONField(default=dict)

    class Meta:
        db_table = "index_validations"
        constraints = [
            choices_check("validation_type", IndexValidationType, "index_validation_type_valid"),
            choices_check("status", IndexValidationStatus, "index_validation_status_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.validation_type} {self.status}"
