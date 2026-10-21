from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasPerm
from apps.documents.selectors import visible_documents

from . import serializers as s
from . import services
from .models import ProcessingJob


def jobs_for(user):
    """Jobs of documents the user may see (so a job never reveals a hidden document)."""
    return ProcessingJob.objects.filter(document_version__document__in=visible_documents(user).values("pk")).select_related(
        "document_version__document", "pipeline_version__pipeline"
    )


class JobListView(generics.ListAPIView):
    permission_classes = [HasPerm("jobs.view")]
    serializer_class = s.JobSerializer
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = jobs_for(self.request.user)
        if value := self.request.query_params.get("document"):
            qs = qs.filter(document_version__document_id=value)
        if value := self.request.query_params.get("status"):
            qs = qs.filter(status=value)
        return qs


class JobDetailView(generics.RetrieveAPIView):
    permission_classes = [HasPerm("jobs.view")]
    serializer_class = s.JobDetailSerializer

    def get_queryset(self):
        return jobs_for(self.request.user).prefetch_related("step_runs")


class JobRetryView(APIView):
    permission_classes = [HasPerm("jobs.retry")]

    @extend_schema(request=None, responses=s.JobDetailSerializer)
    def post(self, request, pk):
        job = generics.get_object_or_404(jobs_for(request.user), pk=pk)
        services.retry(job, by=request.user, request=request)
        return Response(s.JobDetailSerializer(job).data)


class JobCancelView(APIView):
    permission_classes = [HasPerm("jobs.retry")]

    @extend_schema(request=None, responses=s.JobDetailSerializer)
    def post(self, request, pk):
        job = generics.get_object_or_404(jobs_for(request.user), pk=pk)
        services.cancel(job, by=request.user, request=request)
        return Response(s.JobDetailSerializer(job).data)
