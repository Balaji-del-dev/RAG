from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasPerm, HasPerms
from apps.core import outbox

from . import serializers as s
from . import services
from .models import IndexGeneration


def _generations():
    return IndexGeneration.objects.select_related("pipeline_version__pipeline").order_by("-generation_number")


class GenerationListView(APIView):
    permission_classes = [HasPerms("indexes.view", "indexes.build")]

    @extend_schema(responses=s.GenerationSerializer(many=True))
    def get(self, request):
        return Response(s.GenerationSerializer(_generations(), many=True).data)

    @extend_schema(request=s.BuildRequestSerializer, responses={202: s.GenerationDetailSerializer})
    def post(self, request):
        data = s.BuildRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        job = services.start_build(data.validated_data["pipeline_version"], by=request.user, request=request)
        return Response(
            s.GenerationDetailSerializer(_generations().get(pk=job.index_generation_id)).data, status=status.HTTP_202_ACCEPTED
        )


class GenerationDetailView(generics.RetrieveAPIView):
    permission_classes = [HasPerm("indexes.view")]
    serializer_class = s.GenerationDetailSerializer

    def get_queryset(self):
        return _generations().prefetch_related("build_jobs")


class ValidateView(APIView):
    permission_classes = [HasPerm("indexes.build")]

    @extend_schema(request=None, responses={202: None})
    def post(self, request, pk):
        generation = generics.get_object_or_404(IndexGeneration, pk=pk)
        with transaction.atomic():
            outbox.emit("index.validate", generation, {"generation_id": str(generation.pk)})
        return Response({"queued": True}, status=status.HTTP_202_ACCEPTED)


class PublishView(APIView):
    permission_classes = [HasPerm("releases.approve")]

    @extend_schema(request=None, responses=s.GenerationDetailSerializer)
    def post(self, request, pk):
        generation = services.publish(generics.get_object_or_404(IndexGeneration, pk=pk), by=request.user, request=request)
        return Response(s.GenerationDetailSerializer(_generations().get(pk=generation.pk)).data)


class RollbackView(APIView):
    permission_classes = [HasPerm("releases.approve")]

    @extend_schema(request=None, responses=s.GenerationDetailSerializer)
    def post(self, request, pk):
        generation = services.rollback(generics.get_object_or_404(IndexGeneration, pk=pk), by=request.user, request=request)
        return Response(s.GenerationDetailSerializer(_generations().get(pk=generation.pk)).data)
