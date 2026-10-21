"""Pipeline versions and settings: drafts are edited, published versions never change."""

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from pydantic import ValidationError as PydanticError
from rest_framework.exceptions import ValidationError

from apps.core import audit
from apps.core.exceptions import Conflict

from .components import COMPONENTS, GENERATION_CONFIGS, INGESTION_TYPES, RetrievalSettings
from .models import (
    ComponentDefinition,
    GenerationDefinition,
    PipelineDefinition,
    PipelineStep,
    PipelineVersion,
    RetrievalDefinition,
)

FROZEN = [PipelineVersion.Status.PUBLISHED, PipelineVersion.Status.RETIRED]


def _pydantic_errors(error: PydanticError, prefix: str = "") -> dict:
    details: dict[str, list[str]] = {}
    for item in error.errors():
        field = ".".join(str(part) for part in (prefix, *item["loc"]) if part != "")
        details.setdefault(field or "non_field_errors", []).append(item["msg"])
    return details


def require_draft(version: PipelineVersion) -> None:
    if version.status != PipelineVersion.Status.DRAFT:
        raise Conflict("Published versions can't be changed. Clone it into a new draft.", code="version_published")


def live_version(pipeline: PipelineDefinition | None = None) -> PipelineVersion | None:
    """The PUBLISHED version of the active pipeline (or of the given one)."""
    query = PipelineVersion.objects.filter(status=PipelineVersion.Status.PUBLISHED)
    query = query.filter(pipeline=pipeline) if pipeline else query.filter(pipeline__is_active=True)
    return query.select_related("pipeline", "retrieval_definition", "generation_definition__model").first()


@transaction.atomic
def clone_version(source: PipelineVersion, *, by, request=None) -> PipelineVersion:
    PipelineDefinition.objects.select_for_update().get(pk=source.pipeline_id)  # serialise version numbers
    number = (PipelineVersion.objects.filter(pipeline=source.pipeline).aggregate(n=Max("version_number"))["n"] or 0) + 1
    draft = PipelineVersion.objects.create(
        pipeline=source.pipeline,
        version_number=number,
        status=PipelineVersion.Status.DRAFT,
        config_json=dict(source.config_json),
        retrieval_definition=source.retrieval_definition,
        generation_definition=source.generation_definition,
        created_by=by,
    )
    PipelineStep.objects.bulk_create(
        PipelineStep(
            pipeline_version=draft,
            component=step.component,
            step_order=step.step_order,
            config_json=dict(step.config_json),
            is_enabled=step.is_enabled,
        )
        for step in source.steps.all()
    )
    audit.record(
        "pipeline_version.cloned",
        actor=by,
        entity_type="pipeline_version",
        entity_id=draft.pk,
        details={"from": str(source.pk), "version_number": number},
        request=request,
    )
    return draft


@transaction.atomic
def update_draft(version: PipelineVersion, *, by, request=None, **changes) -> PipelineVersion:
    require_draft(version)
    fields = []
    if "config_json" in changes:
        version.config_json = changes["config_json"]
        fields.append("config_json")
    if "retrieval_definition" in changes:
        version.retrieval_definition = changes["retrieval_definition"]
        fields.append("retrieval_definition")
    if "generation_definition" in changes:
        version.generation_definition = changes["generation_definition"]
        fields.append("generation_definition")
    if fields:
        version.save(update_fields=fields)
        audit.record(
            "pipeline_version.updated", actor=by, entity_type="pipeline_version", entity_id=version.pk,
            details={"fields": fields}, request=request,
        )  # fmt: skip
    return version


@transaction.atomic
def replace_steps(version: PipelineVersion, steps: list[dict], *, by, request=None) -> list[PipelineStep]:
    """Replace the ordered ingestion steps of a draft. Each step: {component, config, is_enabled}."""
    require_draft(version)
    if not steps:
        raise ValidationError({"steps": ["A pipeline needs at least one step."]})
    errors: dict[str, list[str]] = {}
    rows = []
    for index, step in enumerate(steps):
        key = step.get("component", "")
        component = COMPONENTS.get(key)
        if component is None or component.type not in INGESTION_TYPES:
            errors[f"steps.{index}.component"] = [f"'{key}' is not an ingestion component on the allow-list."]
            continue
        try:
            config = component.config.model_validate(step.get("config") or {}).model_dump()
        except PydanticError as exc:
            errors.update(_pydantic_errors(exc, f"steps.{index}.config"))
            continue
        rows.append((key, config, bool(step.get("is_enabled", True))))
    if errors:
        raise ValidationError(errors)
    definitions = {c.name: c for c in ComponentDefinition.objects.filter(name__in=[key for key, _, _ in rows])}
    PipelineStep.objects.filter(pipeline_version=version).delete()
    created = PipelineStep.objects.bulk_create(
        PipelineStep(
            pipeline_version=version, component=definitions[key], step_order=order, config_json=config, is_enabled=enabled
        )
        for order, (key, config, enabled) in enumerate(rows, start=1)
    )
    audit.record(
        "pipeline_version.steps_replaced", actor=by, entity_type="pipeline_version", entity_id=version.pk,
        details={"steps": [key for key, _, _ in rows]}, request=request,
    )  # fmt: skip
    return created


@transaction.atomic
def publish_initial(version: PipelineVersion, *, by, request=None) -> PipelineVersion:
    """Publish the very first version of a pipeline (no baseline exists yet to evaluate against)."""
    require_draft(version)
    if PipelineVersion.objects.filter(pipeline=version.pipeline).filter(status__in=FROZEN).exists():
        raise Conflict(
            "This pipeline already has a published version. New versions are released through evaluation and approval.",
            code="not_initial",
        )
    if not version.steps.filter(is_enabled=True).exists():
        raise Conflict("The version has no enabled steps.", code="no_steps")
    version.status = PipelineVersion.Status.PUBLISHED
    version.published_by = by
    version.published_at = timezone.now()
    version.save(update_fields=["status", "published_by", "published_at"])
    audit.record(
        "pipeline_version.published", actor=by, entity_type="pipeline_version", entity_id=version.pk,
        details={"initial": True, "version_number": version.version_number}, request=request,
    )  # fmt: skip
    return version


# ---------------------------------------------------------------- retrieval and generation settings


def _in_use(definition, field: str) -> bool:
    return PipelineVersion.objects.filter(**{field: definition}, status__in=FROZEN).exists()


def validate_retrieval(data: dict) -> dict:
    try:
        return RetrievalSettings.model_validate(data).model_dump()
    except PydanticError as exc:
        raise ValidationError(_pydantic_errors(exc))


def validate_generation(data: dict) -> dict:
    errors: dict[str, list[str]] = {}
    clean = {}
    for field, model in GENERATION_CONFIGS.items():
        try:
            clean[field] = model.model_validate(data.get(field) or {}).model_dump()
        except PydanticError as exc:
            errors.update(_pydantic_errors(exc, field))
    if errors:
        raise ValidationError(errors)
    return clean


def save_retrieval_definition(definition: RetrievalDefinition | None, *, name: str, configs: dict, by, request=None):
    if definition is not None and _in_use(definition, "retrieval_definition"):
        raise Conflict("These settings are used by a published version. Create new settings instead.", code="definition_in_use")
    clean = validate_retrieval(configs)
    if RetrievalDefinition.objects.filter(name=name).exclude(pk=getattr(definition, "pk", None)).exists():
        raise ValidationError({"name": ["This name is taken."]})
    definition = definition or RetrievalDefinition()
    definition.name = name
    for field, value in clean.items():
        setattr(definition, field, value)
    definition.save()
    audit.record(
        "retrieval_definition.saved", actor=by, entity_type="retrieval_definition", entity_id=definition.pk, request=request
    )
    return definition


def save_generation_definition(
    definition: GenerationDefinition | None, *, name: str, model, prompt_template: str, configs: dict, by, request=None
):
    if definition is not None and _in_use(definition, "generation_definition"):
        raise Conflict("These settings are used by a published version. Create new settings instead.", code="definition_in_use")
    if model.model_type != "LLM":
        raise ValidationError({"model_id": ["Choose an LLM."]})
    if "{sources}" not in prompt_template or "{question}" not in prompt_template:
        raise ValidationError({"prompt_template": ["The prompt must contain {sources} and {question}."]})
    clean = validate_generation(configs)
    if GenerationDefinition.objects.filter(name=name).exclude(pk=getattr(definition, "pk", None)).exists():
        raise ValidationError({"name": ["This name is taken."]})
    definition = definition or GenerationDefinition()
    definition.name, definition.model, definition.prompt_template = name, model, prompt_template
    for field, value in clean.items():
        setattr(definition, field, value)
    definition.save()
    audit.record(
        "generation_definition.saved", actor=by, entity_type="generation_definition", entity_id=definition.pk, request=request
    )
    return definition
