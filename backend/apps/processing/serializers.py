from rest_framework import serializers

from .models import ProcessingJob, ProcessingStepRun


class StepRunSerializer(serializers.ModelSerializer):
    attempt = serializers.SerializerMethodField()

    class Meta:
        model = ProcessingStepRun
        fields = ["id", "step_name", "status", "attempt", "input_summary", "output_summary", "duration_ms", "error_message"]

    def get_attempt(self, row) -> int:
        return int((row.input_summary or {}).get("attempt", 1))


class JobSerializer(serializers.ModelSerializer):
    document_id = serializers.UUIDField(source="document_version.document_id", read_only=True)
    filename = serializers.CharField(source="document_version.document.filename", read_only=True)
    version_number = serializers.IntegerField(source="document_version.version_number", read_only=True)
    pipeline_version = serializers.SerializerMethodField()

    class Meta:
        model = ProcessingJob
        fields = [
            "id", "document_id", "filename", "version_number", "pipeline_version", "job_type", "status",
            "attempt_count", "created_at", "started_at", "completed_at", "error_message",
        ]  # fmt: skip

    def get_pipeline_version(self, job) -> str:
        return f"{job.pipeline_version.pipeline.name} v{job.pipeline_version.version_number}"


class JobDetailSerializer(JobSerializer):
    steps = serializers.SerializerMethodField()

    class Meta(JobSerializer.Meta):
        fields = [*JobSerializer.Meta.fields, "steps"]

    def get_steps(self, job) -> list[dict]:
        """The step runs of the latest attempt, in order."""
        rows = list(job.step_runs.all())
        latest = max((int((r.input_summary or {}).get("attempt", 1)) for r in rows), default=1)
        rows = [r for r in rows if int((r.input_summary or {}).get("attempt", 1)) == latest]
        rows.sort(key=lambda r: (r.input_summary or {}).get("step_order", 0))
        return StepRunSerializer(rows, many=True).data
