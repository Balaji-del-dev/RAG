from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasPerm
from apps.core import audit
from apps.documents.selectors import visible_documents
from apps.processing.models import Chunk

from . import serializers as s
from .models import AnswerRecord, FailureCase, RetrievalRun, UserFeedback


def runs_for(user):
    qs = RetrievalRun.objects.select_related("user", "pipeline_version__pipeline", "index_generation").prefetch_related("answers")
    return qs if user.has_perm("evaluation.view") else qs.filter(user=user)


class RunListView(generics.ListAPIView):
    permission_classes = [HasPerm("rag.ask")]
    serializer_class = s.RunSerializer
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = runs_for(self.request.user)
        if self.request.query_params.get("mine") == "1":
            qs = qs.filter(user=self.request.user)
        if value := self.request.query_params.get("status"):
            qs = qs.filter(status=value)
        return qs


class RunDetailView(generics.RetrieveAPIView):
    permission_classes = [HasPerm("rag.ask")]
    serializer_class = s.RunDetailSerializer

    def get_queryset(self):
        return runs_for(self.request.user)


class ChunkView(APIView):
    """The citation viewer: a chunk's text, only if its document is visible to the user."""

    permission_classes = [HasPerm("documents.view")]

    @extend_schema(responses=s.ChunkSerializer)
    def get(self, request, pk):
        chunk = generics.get_object_or_404(
            Chunk.objects.select_related("document_version__document").filter(
                document_version__document__in=visible_documents(request.user).values("pk")
            ),
            pk=pk,
        )
        return Response(s.ChunkSerializer(chunk).data)


class FeedbackView(APIView):
    permission_classes = [HasPerm("feedback.create")]

    @extend_schema(request=s.FeedbackSerializer, responses=s.FeedbackOutSerializer)
    def post(self, request, pk):
        answer = generics.get_object_or_404(
            AnswerRecord.objects.select_related("retrieval_run"), pk=pk, retrieval_run__user=request.user
        )
        data = s.FeedbackSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        rating = data.validated_data["rating"]
        text = data.validated_data.get("feedback_text") or None
        with transaction.atomic():
            row, _ = UserFeedback.objects.update_or_create(
                answer=answer, user=request.user, defaults={"rating": rating, "feedback_text": text}
            )
            if rating <= 2 and not FailureCase.objects.filter(retrieval_run=answer.retrieval_run).exists():
                FailureCase.objects.create(
                    retrieval_run=answer.retrieval_run,
                    failure_type=data.validated_data.get("problem") or FailureCase.Type.INCOMPLETE,
                    root_cause=f"User feedback ({rating}/5): {text}" if text else f"User feedback ({rating}/5)",
                )
            audit.record("answer.feedback", actor=request.user, entity_type="answer", entity_id=answer.pk, request=request,
                         details={"rating": rating})  # fmt: skip
        return Response(s.FeedbackOutSerializer(row).data)


class FailureCaseListView(generics.ListAPIView):
    permission_classes = [HasPerm("failures.review")]
    serializer_class = s.FailureCaseSerializer
    ordering = ["review_status", "-retrieval_run__created_at"]

    def get_queryset(self):
        qs = FailureCase.objects.select_related("retrieval_run__user")
        if value := self.request.query_params.get("review_status"):
            qs = qs.filter(review_status=value)
        if value := self.request.query_params.get("failure_type"):
            qs = qs.filter(failure_type=value)
        return qs


class FailureCaseDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [HasPerm("failures.review")]
    serializer_class = s.FailureCaseSerializer
    queryset = FailureCase.objects.select_related("retrieval_run__user")
    http_method_names = ["get", "patch"]

    def perform_update(self, serializer):
        case = serializer.save()
        audit.record("failure_case.reviewed", actor=self.request.user, entity_type="failure_case", entity_id=case.pk,
                     request=self.request, details={"review_status": case.review_status})  # fmt: skip
