"""4.3 Processing & canonical chunks. Full chunk text lives here; vectors live in Qdrant."""

import uuid

from django.db import models
from django.utils import timezone

from apps.core.models import choices_check


class JobStatus(models.TextChoices):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRY = "RETRY"
    CANCELLED = "CANCELLED"


class ProcessingJobType(models.TextChoices):
    INGEST = "INGEST"
    REPROCESS = "REPROCESS"


class ProcessingJob(models.Model):
    JobType = ProcessingJobType

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_version = models.ForeignKey("documents.DocumentVersion", on_delete=models.PROTECT, related_name="processing_jobs")
    pipeline_version = models.ForeignKey("registry.PipelineVersion", on_delete=models.PROTECT, related_name="processing_jobs")
    job_type = models.CharField(max_length=20, choices=JobType.choices, default=JobType.INGEST)
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.QUEUED)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "processing_jobs"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"], name="processing_job_status_idx")]
        constraints = [
            choices_check("status", JobStatus, "processing_job_status_valid"),
            choices_check("job_type", ProcessingJobType, "processing_job_type_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.job_type} {self.document_version_id} ({self.status})"


class ProcessingStepRunStatus(models.TextChoices):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ProcessingStepRun(models.Model):
    Status = ProcessingStepRunStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    processing_job = models.ForeignKey(ProcessingJob, on_delete=models.CASCADE, related_name="step_runs")
    step_name = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    input_summary = models.JSONField(default=dict)
    output_summary = models.JSONField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "processing_step_runs"
        constraints = [choices_check("status", ProcessingStepRunStatus, "step_run_status_valid")]

    def __str__(self) -> str:
        return f"{self.step_name} ({self.status})"


class DocumentElementType(models.TextChoices):
    TITLE = "TITLE"
    HEADING = "HEADING"
    PARAGRAPH = "PARAGRAPH"
    LIST_ITEM = "LIST_ITEM"
    TABLE = "TABLE"
    CAPTION = "CAPTION"
    CODE = "CODE"
    FOOTNOTE = "FOOTNOTE"
    PAGE_HEADER = "PAGE_HEADER"
    PAGE_FOOTER = "PAGE_FOOTER"


class DocumentElement(models.Model):
    Type = DocumentElementType

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_version = models.ForeignKey("documents.DocumentVersion", on_delete=models.CASCADE, related_name="elements")
    element_type = models.CharField(max_length=20, choices=Type.choices)
    element_order = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField(null=True, blank=True)
    section_path = models.TextField(null=True, blank=True)
    text_content = models.TextField()
    metadata_json = models.JSONField(default=dict)

    class Meta:
        db_table = "document_elements"
        ordering = ["document_version", "element_order"]
        indexes = [models.Index(fields=["document_version", "element_order"], name="document_element_order_idx")]
        constraints = [choices_check("element_type", DocumentElementType, "element_type_valid")]

    def __str__(self) -> str:
        return f"{self.element_type} #{self.element_order}"


class Chunk(models.Model):
    """Canonical chunk. The ID is uuid5(document_version · pipeline_version · chunk_index · content_hash)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_version = models.ForeignKey("documents.DocumentVersion", on_delete=models.PROTECT, related_name="chunks")
    pipeline_version = models.ForeignKey("registry.PipelineVersion", on_delete=models.PROTECT, related_name="chunks")
    parent_chunk = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    chunk_index = models.PositiveIntegerField()
    text_content = models.TextField()
    token_count = models.PositiveIntegerField()
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)
    section_path = models.TextField(null=True, blank=True)
    content_hash = models.CharField(max_length=64)
    metadata_json = models.JSONField(default=dict)

    class Meta:
        db_table = "chunks"
        ordering = ["document_version", "chunk_index"]
        constraints = [
            models.UniqueConstraint(fields=["document_version", "pipeline_version", "chunk_index"], name="chunk_position_unique"),
            models.CheckConstraint(
                condition=models.Q(page_start__isnull=True)
                | models.Q(page_end__isnull=True)
                | models.Q(page_end__gte=models.F("page_start")),
                name="chunk_pages_ordered",
            ),
        ]

    def __str__(self) -> str:
        return f"chunk {self.chunk_index} of {self.document_version_id}"


class ChunkRelationshipType(models.TextChoices):
    NEXT = "NEXT"
    PARENT = "PARENT"
    SAME_TABLE = "SAME_TABLE"


class ChunkRelationship(models.Model):
    Type = ChunkRelationshipType

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_chunk = models.ForeignKey(Chunk, on_delete=models.CASCADE, related_name="outgoing_relationships")
    target_chunk = models.ForeignKey(Chunk, on_delete=models.CASCADE, related_name="incoming_relationships")
    relationship_type = models.CharField(max_length=20, choices=Type.choices)

    class Meta:
        db_table = "chunk_relationships"
        constraints = [
            models.UniqueConstraint(
                fields=["source_chunk", "target_chunk", "relationship_type"], name="chunk_relationship_unique"
            ),
            choices_check("relationship_type", ChunkRelationshipType, "chunk_relationship_type_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.source_chunk_id} {self.relationship_type} {self.target_chunk_id}"


class EmbeddingRecordStatus(models.TextChoices):
    PENDING = "PENDING"
    EMBEDDED = "EMBEDDED"
    FAILED = "FAILED"


class EmbeddingRecord(models.Model):
    Status = EmbeddingRecordStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chunk = models.ForeignKey(Chunk, on_delete=models.CASCADE, related_name="embeddings")
    model = models.ForeignKey("registry.ModelDefinition", on_delete=models.PROTECT, related_name="embedding_records")
    model_version = models.CharField(max_length=80, db_index=True)
    vector_dimension = models.PositiveIntegerField()
    vector_point_id = models.UUIDField()
    content_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        db_table = "embedding_records"
        constraints = [
            models.UniqueConstraint(fields=["chunk", "model", "model_version"], name="embedding_record_unique"),
            choices_check("status", EmbeddingRecordStatus, "embedding_status_valid"),
        ]

    def __str__(self) -> str:
        return f"embedding of {self.chunk_id} ({self.model_version})"
