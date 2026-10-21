from apps.accounts.admin_site import register

from .models import (
    ComponentDefinition,
    GenerationDefinition,
    ModelDefinition,
    PipelineDefinition,
    PipelineStep,
    PipelineVersion,
    RetrievalDefinition,
)

FROZEN = [PipelineVersion.Status.PUBLISHED, PipelineVersion.Status.RETIRED]


def is_frozen(obj) -> bool:
    """A published or retired version is what was evaluated and approved: it, its steps and its settings stay as they are
    (the database enforces it for pipeline_versions). Clone a draft on the Pipelines page to change them."""
    if obj is None:
        return False
    if isinstance(obj, PipelineVersion):
        return obj.status in FROZEN
    if isinstance(obj, PipelineStep):
        return obj.pipeline_version.status in FROZEN
    return obj.pipeline_versions.filter(status__in=FROZEN).exists()


class FrozenWhenPublished:
    def has_change_permission(self, request, obj=None) -> bool:
        return not is_frozen(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None) -> bool:
        return not is_frozen(obj) and super().has_delete_permission(request, obj)


register(PipelineDefinition, ComponentDefinition, ModelDefinition)
register(PipelineVersion, PipelineStep, RetrievalDefinition, GenerationDefinition, mixins=(FrozenWhenPublished,))
