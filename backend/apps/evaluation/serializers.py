from rest_framework import serializers

from apps.indexing.models import IndexGeneration
from apps.registry.models import PipelineVersion

from .models import AuditEvent, EvaluationCase, EvaluationDataset, EvaluationResult, EvaluationRun


class DatasetSerializer(serializers.ModelSerializer):
    case_count = serializers.SerializerMethodField()
    frozen = serializers.SerializerMethodField()

    class Meta:
        model = EvaluationDataset
        fields = ["id", "name", "version", "description", "case_count", "frozen"]

    def get_case_count(self, d) -> int:
        return d.cases.count()

    def get_frozen(self, d) -> bool:
        return d.runs.exists()


class DatasetCreateSerializer(serializers.Serializer):
    name = serializers.RegexField(r"^[\w .-]{2,100}$")
    description = serializers.CharField(required=False, allow_blank=True, default="")


class CaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationCase
        fields = ["id", "dataset", "question", "expected_answer", "expected_sources", "case_type", "metadata_json"]
        read_only_fields = ["id", "dataset"]

    def validate_expected_sources(self, value):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError("A list of file names or document IDs.")
        return value


class ImportSerializer(serializers.Serializer):
    file = serializers.FileField()


class RunCreateSerializer(serializers.Serializer):
    dataset_id = serializers.PrimaryKeyRelatedField(queryset=EvaluationDataset.objects.all(), source="dataset")
    pipeline_version_id = serializers.PrimaryKeyRelatedField(queryset=PipelineVersion.objects.all(), source="pipeline_version")
    index_generation_id = serializers.PrimaryKeyRelatedField(queryset=IndexGeneration.objects.all(), source="generation")
    use_llm_judge = serializers.BooleanField(default=False)


class RunSerializer(serializers.ModelSerializer):
    dataset_label = serializers.CharField(source="dataset.__str__", read_only=True)
    pipeline_version_label = serializers.SerializerMethodField()
    pipeline_version_author = serializers.CharField(source="pipeline_version.created_by.username", default=None, read_only=True)
    generation_number = serializers.IntegerField(source="index_generation.generation_number", read_only=True)
    approved_by = serializers.CharField(source="approved_by.username", default=None, read_only=True)
    is_live = serializers.SerializerMethodField()

    class Meta:
        model = EvaluationRun
        fields = [
            "id", "dataset", "dataset_label", "pipeline_version", "pipeline_version_label", "pipeline_version_author",
            "index_generation", "generation_number", "status", "summary_json", "started_at", "completed_at", "approved_by",
            "is_live",
        ]  # fmt: skip

    def get_pipeline_version_label(self, run) -> str:
        return f"{run.pipeline_version.pipeline.name} v{run.pipeline_version.version_number}"

    def get_is_live(self, run) -> bool:
        """This run measured the live version and generation (it is a baseline, not a release candidate)."""
        return run.pipeline_version.status == "PUBLISHED" and run.index_generation.status == "PUBLISHED"


class ResultSerializer(serializers.ModelSerializer):
    question = serializers.CharField(source="evaluation_case.question", read_only=True)
    case_type = serializers.CharField(source="evaluation_case.case_type", read_only=True)

    class Meta:
        model = EvaluationResult
        fields = ["id", "evaluation_case", "question", "case_type", "metric_name", "score", "passed", "details_json"]


class RunDetailSerializer(RunSerializer):
    results = serializers.SerializerMethodField()

    class Meta(RunSerializer.Meta):
        fields = [*RunSerializer.Meta.fields, "results"]

    def get_results(self, run) -> list[dict]:
        rows = run.results.select_related("evaluation_case").order_by("evaluation_case_id", "metric_name")
        return ResultSerializer(rows, many=True).data


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "created_at",
            "actor",
            "actor_user",
            "event_type",
            "entity_type",
            "entity_id",
            "ip_address",
            "details_json",
        ]
