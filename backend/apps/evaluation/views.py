from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasPerm, HasPerms

from . import serializers as s
from . import services
from .models import AuditEvent, EvaluationCase, EvaluationDataset, EvaluationRun

DatasetPerms = [HasPerms("evaluation.view", "evaluation.manage_datasets")]


class DatasetListView(APIView):
    permission_classes = DatasetPerms

    @extend_schema(responses=s.DatasetSerializer(many=True))
    def get(self, request):
        return Response(s.DatasetSerializer(EvaluationDataset.objects.order_by("name", "-version"), many=True).data)

    @extend_schema(request=s.DatasetCreateSerializer, responses={201: s.DatasetSerializer})
    def post(self, request):
        data = s.DatasetCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        dataset = services.create_dataset(**data.validated_data, by=request.user, request=request)
        return Response(s.DatasetSerializer(dataset).data, status=status.HTTP_201_CREATED)


class DatasetDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = DatasetPerms
    serializer_class = s.DatasetSerializer
    queryset = EvaluationDataset.objects.all()
    http_method_names = ["get", "patch"]


class CaseListView(APIView):
    permission_classes = DatasetPerms

    @extend_schema(responses=s.CaseSerializer(many=True))
    def get(self, request, pk):
        dataset = generics.get_object_or_404(EvaluationDataset, pk=pk)
        return Response(s.CaseSerializer(dataset.cases.order_by("id"), many=True).data)

    @extend_schema(request=s.CaseSerializer, responses={201: s.CaseSerializer})
    def post(self, request, pk):
        dataset = generics.get_object_or_404(EvaluationDataset, pk=pk)
        services.require_editable(dataset)
        data = s.CaseSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(s.CaseSerializer(data.save(dataset=dataset)).data, status=status.HTTP_201_CREATED)


class CaseDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = DatasetPerms
    serializer_class = s.CaseSerializer
    queryset = EvaluationCase.objects.select_related("dataset")
    http_method_names = ["get", "patch", "delete"]

    def perform_update(self, serializer):
        services.require_editable(serializer.instance.dataset)
        serializer.save()

    def perform_destroy(self, case):
        services.require_editable(case.dataset)
        case.delete()


class ImportView(APIView):
    permission_classes = [HasPerm("evaluation.manage_datasets")]
    parser_classes = [MultiPartParser]

    @extend_schema(request={"multipart/form-data": s.ImportSerializer}, responses=s.CaseSerializer(many=True))
    def post(self, request, pk):
        dataset = generics.get_object_or_404(EvaluationDataset, pk=pk)
        services.require_editable(dataset)
        data = s.ImportSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        upload = data.validated_data["file"]
        cases = services.parse_cases(upload.name, upload.read())
        created = EvaluationCase.objects.bulk_create(EvaluationCase(dataset=dataset, **c) for c in cases)
        return Response(s.CaseSerializer(created, many=True).data, status=status.HTTP_201_CREATED)


class NewVersionView(APIView):
    permission_classes = [HasPerm("evaluation.manage_datasets")]

    @extend_schema(request=None, responses={201: s.DatasetSerializer})
    def post(self, request, pk):
        dataset = services.new_version(generics.get_object_or_404(EvaluationDataset, pk=pk), by=request.user, request=request)
        return Response(s.DatasetSerializer(dataset).data, status=status.HTTP_201_CREATED)


class FromFailuresView(APIView):
    permission_classes = [HasPerm("evaluation.manage_datasets")]

    @extend_schema(request=None, responses={201: s.DatasetSerializer})
    def post(self, request, pk):
        dataset = services.version_from_failures(
            generics.get_object_or_404(EvaluationDataset, pk=pk), by=request.user, request=request
        )
        return Response(s.DatasetSerializer(dataset).data, status=status.HTTP_201_CREATED)


def _runs():
    return EvaluationRun.objects.select_related(
        "dataset", "pipeline_version__pipeline", "pipeline_version__created_by", "index_generation", "approved_by"
    )


class RunListView(APIView):
    permission_classes = [HasPerms("evaluation.view", "evaluation.run")]

    @extend_schema(responses=s.RunSerializer(many=True))
    def get(self, request):
        return Response(s.RunSerializer(_runs().order_by("-started_at")[:200], many=True).data)

    @extend_schema(request=s.RunCreateSerializer, responses={202: s.RunSerializer})
    def post(self, request):
        data = s.RunCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        run = services.start_run(**data.validated_data, by=request.user, request=request)
        return Response(s.RunSerializer(_runs().get(pk=run.pk)).data, status=status.HTTP_202_ACCEPTED)


class CandidateListView(APIView):
    """What an evaluation can run on: every generation that is live, building or validating, with its pipeline version."""

    permission_classes = [HasPerm("evaluation.run")]

    @extend_schema(responses=None)
    def get(self, request):
        from apps.indexing.models import IndexGeneration

        rows = IndexGeneration.objects.exclude(status__in=["RETIRED", "FAILED"]).select_related("pipeline_version__pipeline")
        return Response(
            [
                {
                    "index_generation_id": str(g.pk),
                    "generation_number": g.generation_number,
                    "status": g.status,
                    "pipeline_version_id": str(g.pipeline_version_id),
                    "label": f"{g.pipeline_version.pipeline.name} v{g.pipeline_version.version_number}"
                    f" · generation {g.generation_number}" + (" (live)" if g.status == "PUBLISHED" else f" ({g.status.lower()})"),
                }
                for g in rows.order_by("-generation_number")
            ]
        )


class RunDetailView(generics.RetrieveAPIView):
    permission_classes = [HasPerm("evaluation.view")]
    serializer_class = s.RunDetailSerializer

    def get_queryset(self):
        return _runs()


class ApproveView(APIView):
    permission_classes = [HasPerm("releases.approve")]

    @extend_schema(request=None, responses=s.RunSerializer)
    def post(self, request, pk):
        run = services.approve(generics.get_object_or_404(EvaluationRun, pk=pk), by=request.user, request=request)
        return Response(s.RunSerializer(_runs().get(pk=run.pk)).data)


class AuditEventListView(generics.ListAPIView):
    permission_classes = [HasPerm("audit.read")]
    serializer_class = s.AuditEventSerializer

    def get_queryset(self):
        qs = AuditEvent.objects.order_by("-created_at", "-id")
        params = self.request.query_params
        if value := params.get("actor"):
            qs = qs.filter(actor__icontains=value)
        if value := params.get("event_type"):
            qs = qs.filter(event_type__startswith=value)
        if value := params.get("entity_type"):
            qs = qs.filter(entity_type=value)
        if value := params.get("since"):
            qs = qs.filter(created_at__date__gte=value)
        if value := params.get("until"):
            qs = qs.filter(created_at__date__lte=value)
        if value := params.get("search"):
            qs = qs.filter(Q(event_type__icontains=value) | Q(actor__icontains=value))
        return qs
