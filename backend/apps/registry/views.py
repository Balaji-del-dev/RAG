from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasPerm, HasPerms

from . import serializers as s
from . import services
from .models import (
    ComponentDefinition,
    GenerationDefinition,
    ModelDefinition,
    PipelineDefinition,
    PipelineVersion,
    RetrievalDefinition,
)

View_Edit = [HasPerms("pipelines.view", "pipelines.edit")]


def _version(pk) -> PipelineVersion:
    return generics.get_object_or_404(
        PipelineVersion.objects.select_related(
            "pipeline", "retrieval_definition", "generation_definition", "created_by", "published_by"
        ),
        pk=pk,
    )


class PipelineListView(generics.ListAPIView):
    permission_classes = [HasPerm("pipelines.view")]
    serializer_class = s.PipelineSerializer
    pagination_class = None

    def get_queryset(self):
        versions = PipelineVersion.objects.select_related("created_by").order_by("-version_number")
        return PipelineDefinition.objects.prefetch_related(Prefetch("versions", queryset=versions))


class PipelineVersionView(APIView):
    permission_classes = View_Edit

    @extend_schema(responses=s.PipelineVersionSerializer)
    def get(self, request, pk):
        return Response(s.PipelineVersionSerializer(_version(pk)).data)

    @extend_schema(request=s.PipelineVersionUpdateSerializer, responses=s.PipelineVersionSerializer)
    def patch(self, request, pk):
        version = _version(pk)
        data = s.PipelineVersionUpdateSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        services.update_draft(version, by=request.user, request=request, **data.validated_data)
        return Response(s.PipelineVersionSerializer(_version(pk)).data)


class CloneVersionView(APIView):
    permission_classes = [HasPerm("pipelines.edit")]

    @extend_schema(request=None, responses={201: s.PipelineVersionSerializer})
    def post(self, request, pk):
        draft = services.clone_version(_version(pk), by=request.user, request=request)
        return Response(s.PipelineVersionSerializer(_version(draft.pk)).data, status=status.HTTP_201_CREATED)


class StepsView(APIView):
    permission_classes = [HasPerm("pipelines.edit")]

    @extend_schema(request=s.StepsReplaceSerializer, responses=s.PipelineVersionSerializer)
    def put(self, request, pk):
        version = _version(pk)
        data = s.StepsReplaceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.replace_steps(version, data.validated_data["steps"], by=request.user, request=request)
        return Response(s.PipelineVersionSerializer(_version(pk)).data)


class PublishInitialView(APIView):
    permission_classes = [HasPerm("releases.approve")]

    @extend_schema(request=None, responses=s.PipelineVersionSerializer)
    def post(self, request, pk):
        services.publish_initial(_version(pk), by=request.user, request=request)
        return Response(s.PipelineVersionSerializer(_version(pk)).data)


class ComponentListView(generics.ListAPIView):
    permission_classes = [HasPerm("pipelines.view")]
    serializer_class = s.ComponentSerializer
    pagination_class = None
    queryset = ComponentDefinition.objects.filter(is_active=True)


class ModelListView(generics.ListAPIView):
    permission_classes = [HasPerm("pipelines.view")]
    serializer_class = s.ModelDefinitionSerializer
    pagination_class = None
    queryset = ModelDefinition.objects.all()


class RetrievalDefinitionListView(APIView):
    permission_classes = View_Edit

    @extend_schema(responses=s.RetrievalDefinitionSerializer(many=True))
    def get(self, request):
        return Response(s.RetrievalDefinitionSerializer(RetrievalDefinition.objects.all(), many=True).data)

    @extend_schema(request=s.RetrievalDefinitionWriteSerializer, responses={201: s.RetrievalDefinitionSerializer})
    def post(self, request):
        data = s.RetrievalDefinitionWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        name = data.validated_data.pop("name")
        definition = services.save_retrieval_definition(
            None, name=name, configs=data.validated_data, by=request.user, request=request
        )
        return Response(s.RetrievalDefinitionSerializer(definition).data, status=status.HTTP_201_CREATED)


class RetrievalDefinitionDetailView(APIView):
    permission_classes = View_Edit

    @extend_schema(responses=s.RetrievalDefinitionSerializer)
    def get(self, request, pk):
        return Response(s.RetrievalDefinitionSerializer(generics.get_object_or_404(RetrievalDefinition, pk=pk)).data)

    @extend_schema(request=s.RetrievalDefinitionWriteSerializer, responses=s.RetrievalDefinitionSerializer)
    def patch(self, request, pk):
        definition = generics.get_object_or_404(RetrievalDefinition, pk=pk)
        current = s.RetrievalDefinitionSerializer(definition).data
        data = s.RetrievalDefinitionWriteSerializer(data={**current, **request.data})
        data.is_valid(raise_exception=True)
        name = data.validated_data.pop("name")
        definition = services.save_retrieval_definition(
            definition, name=name, configs=data.validated_data, by=request.user, request=request
        )
        return Response(s.RetrievalDefinitionSerializer(definition).data)


class GenerationDefinitionListView(APIView):
    permission_classes = View_Edit

    @extend_schema(responses=s.GenerationDefinitionSerializer(many=True))
    def get(self, request):
        return Response(s.GenerationDefinitionSerializer(GenerationDefinition.objects.select_related("model"), many=True).data)

    @extend_schema(request=s.GenerationDefinitionWriteSerializer, responses={201: s.GenerationDefinitionSerializer})
    def post(self, request):
        data = s.GenerationDefinitionWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        definition = services.save_generation_definition(
            None, name=v.pop("name"), model=v.pop("model"), prompt_template=v.pop("prompt_template"),
            configs=v, by=request.user, request=request,
        )  # fmt: skip
        return Response(s.GenerationDefinitionSerializer(definition).data, status=status.HTTP_201_CREATED)


class GenerationDefinitionDetailView(APIView):
    permission_classes = View_Edit

    @extend_schema(responses=s.GenerationDefinitionSerializer)
    def get(self, request, pk):
        return Response(s.GenerationDefinitionSerializer(generics.get_object_or_404(GenerationDefinition, pk=pk)).data)

    @extend_schema(request=s.GenerationDefinitionWriteSerializer, responses=s.GenerationDefinitionSerializer)
    def patch(self, request, pk):
        definition = generics.get_object_or_404(GenerationDefinition, pk=pk)
        current = s.GenerationDefinitionSerializer(definition).data
        merged = {**current, "model_id": current["model"], **request.data}
        data = s.GenerationDefinitionWriteSerializer(data=merged)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        definition = services.save_generation_definition(
            definition, name=v.pop("name"), model=v.pop("model"), prompt_template=v.pop("prompt_template"),
            configs=v, by=request.user, request=request,
        )  # fmt: skip
        return Response(s.GenerationDefinitionSerializer(definition).data)
