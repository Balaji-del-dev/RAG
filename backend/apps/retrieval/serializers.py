from rest_framework import serializers

from .models import AnswerRecord, FailureCase, RetrievalResult, RetrievalRun, UserFeedback


class AnswerSerializer(serializers.ModelSerializer):
    my_feedback = serializers.SerializerMethodField()

    class Meta:
        model = AnswerRecord
        fields = [
            "id",
            "answer_text",
            "citation_data",
            "status",
            "latency_ms",
            "token_usage_json",
            "prompt_version",
            "my_feedback",
        ]

    def get_my_feedback(self, answer) -> dict | None:
        request = self.context.get("request")
        if request is None:
            return None
        row = answer.feedback.filter(user=request.user).first()
        return {"rating": row.rating, "feedback_text": row.feedback_text} if row else None


class RunSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    answer = serializers.SerializerMethodField()

    class Meta:
        model = RetrievalRun
        fields = ["id", "request_id", "username", "query_text", "status", "latency_ms", "created_at", "answer"]

    def get_answer(self, run) -> dict | None:
        answer = run.answers.order_by("-id").first() if hasattr(run, "answers") else None
        return AnswerSerializer(answer, context=self.context).data if answer else None


class ResultSerializer(serializers.ModelSerializer):
    filename = serializers.CharField(source="chunk.document_version.document.filename", read_only=True)
    page_start = serializers.IntegerField(source="chunk.page_start", read_only=True)
    section_path = serializers.CharField(source="chunk.section_path", read_only=True)

    class Meta:
        model = RetrievalResult
        fields = [
            "chunk",
            "filename",
            "page_start",
            "section_path",
            "retrieval_source",
            "original_rank",
            "original_score",
            "fusion_rank",
            "reranker_score",
        ]


class RunDetailSerializer(RunSerializer):
    results = serializers.SerializerMethodField()
    pipeline_version = serializers.SerializerMethodField()
    generation = serializers.IntegerField(source="index_generation.generation_number", read_only=True)

    class Meta(RunSerializer.Meta):
        fields = [*RunSerializer.Meta.fields, "normalized_query", "pipeline_version", "generation", "trace_id", "results"]

    def get_results(self, run) -> list[dict]:
        rows = run.results.select_related("chunk__document_version__document").order_by("fusion_rank")
        return ResultSerializer(rows, many=True).data

    def get_pipeline_version(self, run) -> str:
        return f"{run.pipeline_version.pipeline.name} v{run.pipeline_version.version_number}"


class FeedbackSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    feedback_text = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    problem = serializers.ChoiceField(
        required=False,
        allow_blank=True,
        choices=["WRONG_RETRIEVAL", "NOT_GROUNDED", "INCOMPLETE", "WRONG_CITATION", "FORMAT", "LATENCY"],
    )


class FeedbackOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserFeedback
        fields = ["id", "rating", "feedback_text", "created_at"]


class FailureCaseSerializer(serializers.ModelSerializer):
    question = serializers.CharField(source="retrieval_run.query_text", read_only=True)
    asked_by = serializers.CharField(source="retrieval_run.user.username", read_only=True)
    asked_at = serializers.DateTimeField(source="retrieval_run.created_at", read_only=True)
    run_status = serializers.CharField(source="retrieval_run.status", read_only=True)

    class Meta:
        model = FailureCase
        fields = [
            "id",
            "retrieval_run",
            "question",
            "asked_by",
            "asked_at",
            "run_status",
            "failure_type",
            "root_cause",
            "review_status",
            "resolution_notes",
        ]
        read_only_fields = ["id", "retrieval_run", "question", "asked_by", "asked_at", "run_status"]


class ChunkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    text_content = serializers.CharField()
    page_start = serializers.IntegerField(allow_null=True)
    page_end = serializers.IntegerField(allow_null=True)
    section_path = serializers.CharField(allow_null=True)
    document_id = serializers.UUIDField(source="document_version.document_id")
    filename = serializers.CharField(source="document_version.document.filename")
    version_number = serializers.IntegerField(source="document_version.version_number")
