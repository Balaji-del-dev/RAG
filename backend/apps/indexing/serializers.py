from django.db.models import Count, Q
from rest_framework import serializers

from apps.registry.models import PipelineVersion

from .models import IndexBuildJob, IndexGeneration, IndexMembership, IndexValidation
from .services import latest_validations, validated


class ValidationSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndexValidation
        fields = ["id", "validation_type", "status", "expected_count", "actual_count", "details_json"]


class BuildJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndexBuildJob
        fields = ["id", "status", "attempt_count", "started_at", "completed_at", "error_message"]


class GenerationSerializer(serializers.ModelSerializer):
    pipeline_version_label = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()
    validated = serializers.SerializerMethodField()

    class Meta:
        model = IndexGeneration
        fields = [
            "id", "generation_number", "pipeline_version", "pipeline_version_label", "qdrant_collection",
            "opensearch_index", "status", "published_at", "counts", "validated",
        ]  # fmt: skip

    def get_pipeline_version_label(self, g) -> str:
        return f"{g.pipeline_version.pipeline.name} v{g.pipeline_version.version_number}"

    def get_counts(self, g) -> dict:
        return IndexMembership.objects.filter(index_generation=g).aggregate(
            chunks=Count("pk", filter=Q(status="INDEXED")),
            documents=Count("document_version__document", filter=Q(status="INDEXED"), distinct=True),
            removed=Count("pk", filter=Q(status="REMOVED")),
        )

    def get_validated(self, g) -> bool:
        return validated(g)


class GenerationDetailSerializer(GenerationSerializer):
    validations = serializers.SerializerMethodField()
    build_jobs = BuildJobSerializer(many=True, read_only=True)

    class Meta(GenerationSerializer.Meta):
        fields = [*GenerationSerializer.Meta.fields, "validations", "build_jobs"]

    def get_validations(self, g) -> list[dict]:
        return ValidationSerializer(sorted(latest_validations(g), key=lambda r: r.id), many=True).data


class BuildRequestSerializer(serializers.Serializer):
    pipeline_version_id = serializers.PrimaryKeyRelatedField(queryset=PipelineVersion.objects.all(), source="pipeline_version")
