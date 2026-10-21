"""4.5 Retrieval, answers & feedback. request_id and trace_id join a run to its logs."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import choices_check


class RetrievalRunStatus(models.TextChoices):
    RUNNING = "RUNNING"
    ANSWERED = "ANSWERED"
    ABSTAINED = "ABSTAINED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class RetrievalRun(models.Model):
    Status = RetrievalRunStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="retrieval_runs")
    query_text = models.TextField()
    normalized_query = models.TextField()
    pipeline_version = models.ForeignKey("registry.PipelineVersion", on_delete=models.PROTECT, related_name="retrieval_runs")
    index_generation = models.ForeignKey("indexing.IndexGeneration", on_delete=models.PROTECT, related_name="retrieval_runs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    latency_ms = models.PositiveIntegerField(default=0)
    trace_id = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "retrieval_runs"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"], name="retrieval_run_user_idx")]
        constraints = [choices_check("status", RetrievalRunStatus, "retrieval_run_status_valid")]

    def __str__(self) -> str:
        return self.query_text[:80]


class RetrievalResultSource(models.TextChoices):
    DENSE = "DENSE"
    LEXICAL = "LEXICAL"
    BOTH = "BOTH"


class RetrievalResult(models.Model):
    Source = RetrievalResultSource

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    retrieval_run = models.ForeignKey(RetrievalRun, on_delete=models.CASCADE, related_name="results")
    chunk = models.ForeignKey("processing.Chunk", on_delete=models.PROTECT, related_name="retrieval_results")
    retrieval_source = models.CharField(max_length=10, choices=Source.choices)
    original_rank = models.PositiveSmallIntegerField()
    original_score = models.FloatField()
    fusion_rank = models.PositiveSmallIntegerField(null=True, blank=True)
    reranker_score = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "retrieval_results"
        indexes = [models.Index(fields=["retrieval_run", "fusion_rank"], name="retrieval_result_rank_idx")]
        constraints = [choices_check("retrieval_source", RetrievalResultSource, "retrieval_source_valid")]

    def __str__(self) -> str:
        return f"{self.retrieval_source} #{self.original_rank} for {self.retrieval_run_id}"


class AnswerRecordStatus(models.TextChoices):
    VALIDATED = "VALIDATED"
    REPAIRED = "REPAIRED"
    ABSTAINED = "ABSTAINED"
    REJECTED = "REJECTED"


class AnswerRecord(models.Model):
    Status = AnswerRecordStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    retrieval_run = models.ForeignKey(RetrievalRun, on_delete=models.CASCADE, related_name="answers")
    model = models.ForeignKey("registry.ModelDefinition", on_delete=models.PROTECT, related_name="answers")
    prompt_version = models.CharField(max_length=40)
    answer_text = models.TextField(null=True, blank=True)
    citation_data = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=Status.choices)
    latency_ms = models.PositiveIntegerField(default=0)
    token_usage_json = models.JSONField(default=dict)

    class Meta:
        db_table = "answer_records"
        constraints = [choices_check("status", AnswerRecordStatus, "answer_status_valid")]

    def __str__(self) -> str:
        return f"answer to {self.retrieval_run_id} ({self.status})"


class UserFeedback(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    answer = models.ForeignKey(AnswerRecord, on_delete=models.CASCADE, related_name="feedback")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="feedback")
    rating = models.PositiveSmallIntegerField()
    feedback_text = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "user_feedback"
        verbose_name_plural = "user feedback"
        constraints = [
            models.UniqueConstraint(fields=["answer", "user"], name="one_feedback_per_user"),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="rating_1_to_5"),
        ]

    def __str__(self) -> str:
        return f"{self.rating}/5 on {self.answer_id}"


class FailureCaseReview(models.TextChoices):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    WONT_FIX = "WONT_FIX"


class FailureCaseType(models.TextChoices):
    NO_RETRIEVAL = "NO_RETRIEVAL"
    WRONG_RETRIEVAL = "WRONG_RETRIEVAL"
    NOT_GROUNDED = "NOT_GROUNDED"
    WRONG_CITATION = "WRONG_CITATION"
    INCOMPLETE = "INCOMPLETE"
    FORMAT = "FORMAT"
    SAFETY = "SAFETY"
    LATENCY = "LATENCY"


class FailureCase(models.Model):
    Type = FailureCaseType

    Review = FailureCaseReview

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    retrieval_run = models.ForeignKey(RetrievalRun, on_delete=models.PROTECT, related_name="failure_cases")
    failure_type = models.CharField(max_length=20, choices=Type.choices)
    root_cause = models.TextField(null=True, blank=True)
    review_status = models.CharField(max_length=20, choices=Review.choices, default=Review.OPEN, db_index=True)
    resolution_notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "failure_cases"
        constraints = [
            choices_check("failure_type", FailureCaseType, "failure_type_valid"),
            choices_check("review_status", FailureCaseReview, "failure_review_status_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.failure_type} ({self.review_status})"
