import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import choices_check


class AuditEvent(models.Model):
    """Append-only audit log. Every app writes it through apps.core.audit.record()."""

    id = models.BigAutoField(primary_key=True)
    event_type = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=60, blank=True)
    entity_id = models.UUIDField(null=True, blank=True)
    actor = models.CharField(max_length=150)
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_events"
        indexes = [models.Index(fields=["entity_type", "entity_id"], name="audit_entity_idx")]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.actor} {self.event_type}"


class EvaluationDataset(models.Model):
    """A named, versioned golden set. A version is frozen once a run has used it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    version = models.PositiveIntegerField(default=1)
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "evaluation_datasets"
        ordering = ["name", "-version"]
        constraints = [models.UniqueConstraint(fields=["name", "version"], name="evaluation_dataset_version_unique")]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class EvaluationCaseType(models.TextChoices):
    FACTUAL = "FACTUAL"
    MULTI_HOP = "MULTI_HOP"
    TABLE = "TABLE"
    NO_ANSWER = "NO_ANSWER"  # must abstain
    ACCESS = "ACCESS"  # must not see a forbidden document
    MULTILINGUAL = "MULTILINGUAL"


class EvaluationCase(models.Model):
    Type = EvaluationCaseType

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(EvaluationDataset, on_delete=models.PROTECT, related_name="cases")
    question = models.TextField()
    expected_answer = models.TextField(null=True, blank=True)
    expected_sources = models.JSONField(default=list)
    case_type = models.CharField(max_length=20, choices=Type.choices, default=Type.FACTUAL)
    metadata_json = models.JSONField(default=dict)

    class Meta:
        db_table = "evaluation_cases"
        constraints = [choices_check("case_type", EvaluationCaseType, "evaluation_case_type_valid")]

    def __str__(self) -> str:
        return self.question[:80]


class EvaluationRunStatus(models.TextChoices):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"  # gates not met
    ERROR = "ERROR"


class EvaluationRun(models.Model):
    Status = EvaluationRunStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dataset = models.ForeignKey(EvaluationDataset, on_delete=models.PROTECT, related_name="runs")
    pipeline_version = models.ForeignKey("registry.PipelineVersion", on_delete=models.PROTECT, related_name="evaluation_runs")
    index_generation = models.ForeignKey("indexing.IndexGeneration", on_delete=models.PROTECT, related_name="evaluation_runs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    summary_json = models.JSONField(default=dict)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+", db_column="approved_by"
    )

    class Meta:
        db_table = "evaluation_runs"
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["pipeline_version", "started_at"], name="evaluation_run_version_idx")]
        constraints = [choices_check("status", EvaluationRunStatus, "evaluation_run_status_valid")]

    def __str__(self) -> str:
        return f"{self.dataset} on {self.pipeline_version} ({self.status})"


class EvaluationResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evaluation_run = models.ForeignKey(EvaluationRun, on_delete=models.CASCADE, related_name="results")
    evaluation_case = models.ForeignKey(EvaluationCase, on_delete=models.PROTECT, related_name="results")
    metric_name = models.CharField(max_length=80, db_index=True)
    score = models.FloatField()
    passed = models.BooleanField()
    details_json = models.JSONField(default=dict)

    class Meta:
        db_table = "evaluation_results"
        constraints = [
            models.UniqueConstraint(fields=["evaluation_run", "evaluation_case", "metric_name"], name="evaluation_result_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.metric_name}={self.score:.3f}"
