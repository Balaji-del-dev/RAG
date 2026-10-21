from rest_framework import serializers

from .components import COMPONENTS
from .models import (
    ComponentDefinition,
    GenerationDefinition,
    ModelDefinition,
    PipelineDefinition,
    PipelineStep,
    PipelineVersion,
    RetrievalDefinition,
)
from .services import FROZEN


class ComponentSerializer(serializers.ModelSerializer):
    key = serializers.CharField(source="name")
    description = serializers.SerializerMethodField()

    class Meta:
        model = ComponentDefinition
        fields = ["id", "key", "component_type", "description", "config_schema", "is_active"]

    def get_description(self, obj) -> str:
        component = COMPONENTS.get(obj.name)
        return component.description if component else ""


class ModelDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelDefinition
        fields = ["id", "name", "provider", "model_name", "model_type", "parameters_json", "is_active"]


class RetrievalDefinitionSerializer(serializers.ModelSerializer):
    in_use = serializers.SerializerMethodField()

    class Meta:
        model = RetrievalDefinition
        fields = ["id", "name", "dense_config", "bm25_config", "fusion_config", "reranker_config", "context_config", "in_use"]

    def get_in_use(self, obj) -> bool:
        return obj.pipeline_versions.filter(status__in=FROZEN).exists()


class RetrievalDefinitionWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    dense_config = serializers.DictField(required=False, default=dict)
    bm25_config = serializers.DictField(required=False, default=dict)
    fusion_config = serializers.DictField(required=False, default=dict)
    reranker_config = serializers.DictField(required=False, default=dict)
    context_config = serializers.DictField(required=False, default=dict)


class GenerationDefinitionSerializer(serializers.ModelSerializer):
    model_name = serializers.CharField(source="model.name", read_only=True)
    in_use = serializers.SerializerMethodField()

    class Meta:
        model = GenerationDefinition
        fields = [
            "id", "name", "model", "model_name", "prompt_template",
            "generation_config", "citation_config", "abstention_config", "in_use",
        ]  # fmt: skip

    def get_in_use(self, obj) -> bool:
        return obj.pipeline_versions.filter(status__in=FROZEN).exists()


class GenerationDefinitionWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    model_id = serializers.PrimaryKeyRelatedField(queryset=ModelDefinition.objects.all(), source="model")
    prompt_template = serializers.CharField()
    generation_config = serializers.DictField(required=False, default=dict)
    citation_config = serializers.DictField(required=False, default=dict)
    abstention_config = serializers.DictField(required=False, default=dict)


class StepSerializer(serializers.ModelSerializer):
    component = serializers.CharField(source="component.name")
    component_type = serializers.CharField(source="component.component_type")
    description = serializers.SerializerMethodField()
    config = serializers.JSONField(source="config_json")

    class Meta:
        model = PipelineStep
        fields = ["id", "step_order", "component", "component_type", "description", "config", "is_enabled"]

    def get_description(self, obj) -> str:
        component = COMPONENTS.get(obj.component.name)
        return component.description if component else ""


class StepWriteSerializer(serializers.Serializer):
    component = serializers.CharField()
    config = serializers.DictField(required=False, default=dict)
    is_enabled = serializers.BooleanField(default=True)


class StepsReplaceSerializer(serializers.Serializer):
    steps = StepWriteSerializer(many=True)


class NamedRef(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class PipelineVersionSerializer(serializers.ModelSerializer):
    pipeline_name = serializers.CharField(source="pipeline.name", read_only=True)
    retrieval_definition = NamedRef(read_only=True)
    generation_definition = NamedRef(read_only=True)
    created_by = serializers.CharField(source="created_by.username", default=None, read_only=True)
    published_by = serializers.CharField(source="published_by.username", default=None, read_only=True)
    steps = serializers.SerializerMethodField()

    class Meta:
        model = PipelineVersion
        fields = [
            "id", "pipeline", "pipeline_name", "version_number", "status", "config_json",
            "retrieval_definition", "generation_definition", "created_by", "published_at", "published_by", "steps",
        ]  # fmt: skip

    def get_steps(self, obj) -> list[dict]:
        steps = obj.steps.select_related("component").order_by("step_order")
        return StepSerializer(steps, many=True).data


class PipelineVersionUpdateSerializer(serializers.Serializer):
    config_json = serializers.DictField(required=False)
    retrieval_definition_id = serializers.PrimaryKeyRelatedField(
        queryset=RetrievalDefinition.objects.all(), source="retrieval_definition", required=False
    )
    generation_definition_id = serializers.PrimaryKeyRelatedField(
        queryset=GenerationDefinition.objects.all(), source="generation_definition", required=False
    )


class VersionSummarySerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", default=None)

    class Meta:
        model = PipelineVersion
        fields = ["id", "version_number", "status", "created_by", "published_at"]


class PipelineSerializer(serializers.ModelSerializer):
    versions = VersionSummarySerializer(many=True, read_only=True)

    class Meta:
        model = PipelineDefinition
        fields = ["id", "name", "description", "is_active", "created_at", "versions"]
