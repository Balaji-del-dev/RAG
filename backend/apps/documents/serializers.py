from rest_framework import serializers

from apps.processing.models import ProcessingJob

from .models import Document, DocumentVersion


class VersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentVersion
        fields = ["id", "version_number", "status", "file_size", "content_sha256"]


class JobSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingJob
        fields = ["id", "job_type", "status", "attempt_count", "created_at", "started_at", "completed_at", "error_message"]


class DocumentSerializer(serializers.ModelSerializer):
    current_version = VersionSerializer(read_only=True)
    access_groups = serializers.SerializerMethodField()
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "filename", "file_extension", "mime_type", "lifecycle_status", "current_version",
            "access_groups", "created_by", "created_at", "updated_at",
        ]  # fmt: skip

    def get_access_groups(self, document) -> list[dict]:
        return [{"id": str(g.access_group_id), "name": g.access_group.name} for g in document.access_grants.all()]


class DocumentDetailSerializer(DocumentSerializer):
    versions = serializers.SerializerMethodField()
    latest_job = serializers.SerializerMethodField()

    class Meta(DocumentSerializer.Meta):
        fields = [*DocumentSerializer.Meta.fields, "versions", "latest_job"]

    def get_versions(self, document) -> list[dict]:
        return VersionSerializer(document.versions.order_by("-version_number"), many=True).data

    def get_latest_job(self, document) -> dict | None:
        job = ProcessingJob.objects.filter(document_version__document=document).order_by("-created_at").first()
        return JobSummarySerializer(job).data if job else None


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=True)
    access_group_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=True, required=False, default=list)


class NewVersionSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=True)


class AccessSerializer(serializers.Serializer):
    access_group_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=True)
