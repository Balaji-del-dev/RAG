"""4.1 Pipeline configuration: pipelines, versions, steps, components, models, retrieval + generation settings."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import choices_check


class PipelineDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "pipeline_definitions"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["is_active"], condition=models.Q(is_active=True), name="one_active_pipeline"),
        ]

    def __str__(self) -> str:
        return self.name


class ComponentDefinitionType(models.TextChoices):
    READER = "READER"
    PARSER = "PARSER"
    OCR = "OCR"
    CLEANER = "CLEANER"
    STRUCTURE = "STRUCTURE"
    ENRICHER = "ENRICHER"
    CHUNKER = "CHUNKER"
    CHUNK_CHECK = "CHUNK_CHECK"
    PERSIST = "PERSIST"
    EMBEDDER = "EMBEDDER"
    RETRIEVER = "RETRIEVER"
    FUSION = "FUSION"
    RERANKER = "RERANKER"
    CONTEXT = "CONTEXT"
    GENERATOR = "GENERATOR"
    VALIDATOR = "VALIDATOR"


class ComponentDefinition(models.Model):
    """The allow-list: implementation_key maps to a class in code, never to a path from the database."""

    Type = ComponentDefinitionType

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    component_type = models.CharField(max_length=20, choices=Type.choices)
    implementation_key = models.CharField(max_length=200)
    config_schema = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "component_definitions"
        ordering = ["component_type", "name"]
        constraints = [choices_check("component_type", ComponentDefinitionType, "component_type_valid")]

    def __str__(self) -> str:
        return self.name


class ModelDefinitionType(models.TextChoices):
    LLM = "LLM"
    EMBEDDING = "EMBEDDING"
    RERANKER = "RERANKER"
    OCR = "OCR"
    LAYOUT = "LAYOUT"


class ModelDefinition(models.Model):
    Type = ModelDefinitionType

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    provider = models.CharField(max_length=60)
    model_name = models.CharField(max_length=200)
    model_type = models.CharField(max_length=20, choices=Type.choices)
    parameters_json = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "model_definitions"
        ordering = ["model_type", "name"]
        constraints = [choices_check("model_type", ModelDefinitionType, "model_type_valid")]

    def __str__(self) -> str:
        return self.name


class RetrievalDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    dense_config = models.JSONField(default=dict)
    bm25_config = models.JSONField(default=dict)
    fusion_config = models.JSONField(default=dict)
    reranker_config = models.JSONField(default=dict)
    context_config = models.JSONField(default=dict)

    class Meta:
        db_table = "retrieval_definitions"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class GenerationDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    model = models.ForeignKey(ModelDefinition, on_delete=models.PROTECT, related_name="generation_definitions")
    prompt_template = models.TextField()
    generation_config = models.JSONField(default=dict)
    citation_config = models.JSONField(default=dict)
    abstention_config = models.JSONField(default=dict)

    class Meta:
        db_table = "generation_definitions"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class PipelineVersionStatus(models.TextChoices):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class PipelineVersion(models.Model):
    Status = PipelineVersionStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline = models.ForeignKey(PipelineDefinition, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    config_json = models.JSONField(default=dict)
    retrieval_definition = models.ForeignKey(RetrievalDefinition, on_delete=models.PROTECT, related_name="pipeline_versions")
    generation_definition = models.ForeignKey(GenerationDefinition, on_delete=models.PROTECT, related_name="pipeline_versions")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+", db_column="created_by"
    )
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+", db_column="published_by"
    )

    class Meta:
        db_table = "pipeline_versions"
        ordering = ["pipeline__name", "-version_number"]
        constraints = [
            models.UniqueConstraint(fields=["pipeline", "version_number"], name="pipeline_version_unique"),
            models.UniqueConstraint(fields=["pipeline"], condition=models.Q(status="PUBLISHED"), name="one_published_version"),
            models.CheckConstraint(condition=models.Q(version_number__gte=1), name="pipeline_version_positive"),
            choices_check("status", PipelineVersionStatus, "pipeline_version_status_valid"),
        ]

    def __str__(self) -> str:
        return f"{self.pipeline} v{self.version_number}"


class PipelineStep(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline_version = models.ForeignKey(PipelineVersion, on_delete=models.CASCADE, related_name="steps")
    component = models.ForeignKey(ComponentDefinition, on_delete=models.PROTECT, related_name="steps")
    step_order = models.PositiveSmallIntegerField()
    config_json = models.JSONField(default=dict)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "pipeline_steps"
        ordering = ["pipeline_version", "step_order"]
        constraints = [models.UniqueConstraint(fields=["pipeline_version", "step_order"], name="pipeline_step_order_unique")]

    def __str__(self) -> str:
        return f"{self.pipeline_version} · {self.step_order}. {self.component}"
