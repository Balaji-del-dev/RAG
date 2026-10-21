from urllib.parse import quote

from django.conf import settings
from django.db.models import Q
from django.http import StreamingHttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasPerm, HasPerms
from apps.core import audit
from apps.core.clients import storage

from . import serializers as s
from . import services
from .selectors import visible_documents
from .validation import FileTooLarge

UPLOAD_SLACK = 1024 * 1024  # multipart framing around the file itself


def _refuse_oversized(request) -> None:
    """Answer 413 from the Content-Length header, before the body is read."""
    length = int(request.META.get("CONTENT_LENGTH") or 0)
    if length > settings.UPLOAD_MAX_BYTES + UPLOAD_SLACK:
        raise FileTooLarge(f"The file is larger than {settings.UPLOAD_MAX_BYTES // (1024 * 1024)} MB.")


def _document(request, pk):
    return generics.get_object_or_404(visible_documents(request.user), pk=pk)  # 404, not 403, outside the user's groups


class DocumentListView(generics.ListAPIView):
    permission_classes = [HasPerms("documents.view", "documents.upload")]
    serializer_class = s.DocumentSerializer
    parser_classes = [MultiPartParser, FormParser]
    ordering_fields = ["created_at", "filename", "updated_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = visible_documents(self.request.user)
        params = self.request.query_params
        if value := params.get("status"):
            qs = qs.filter(lifecycle_status=value)
        if value := params.get("type"):
            qs = qs.filter(file_extension=value.lower())
        if value := params.get("group"):
            qs = qs.filter(access_grants__access_group__name=value)
        if value := params.get("search"):
            qs = qs.filter(Q(filename__icontains=value))
        return qs

    def initial(self, request, *args, **kwargs):
        if request.method == "POST":
            _refuse_oversized(request)
        super().initial(request, *args, **kwargs)

    @extend_schema(request={"multipart/form-data": s.UploadSerializer}, responses={201: s.DocumentDetailSerializer})
    def post(self, request):
        data = s.UploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        document, duplicate = services.upload_document(
            user=request.user,
            uploaded=data.validated_data["file"],
            access_group_ids=data.validated_data["access_group_ids"],
            request=request,
        )
        body = {"duplicate": duplicate, "document": s.DocumentDetailSerializer(_document(request, document.pk)).data}
        return Response(body, status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED)


class DocumentDetailView(APIView):
    permission_classes = [HasPerms("documents.view", "documents.manage")]

    @extend_schema(responses=s.DocumentDetailSerializer)
    def get(self, request, pk):
        return Response(s.DocumentDetailSerializer(_document(request, pk)).data)

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        services.delete_document(user=request.user, document=_document(request, pk), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentVersionsView(APIView):
    permission_classes = [HasPerm("documents.manage")]
    parser_classes = [MultiPartParser, FormParser]

    def initial(self, request, *args, **kwargs):
        _refuse_oversized(request)
        super().initial(request, *args, **kwargs)

    @extend_schema(request={"multipart/form-data": s.NewVersionSerializer}, responses={201: s.DocumentDetailSerializer})
    def post(self, request, pk):
        document = _document(request, pk)
        data = s.NewVersionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.upload_new_version(user=request.user, document=document, uploaded=data.validated_data["file"], request=request)
        return Response(s.DocumentDetailSerializer(_document(request, pk)).data, status=status.HTTP_201_CREATED)


class DocumentAccessView(APIView):
    permission_classes = [HasPerm("documents.manage_access")]

    @extend_schema(request=s.AccessSerializer, responses=s.DocumentDetailSerializer)
    def put(self, request, pk):
        document = _document(request, pk)
        data = s.AccessSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        services.set_access_groups(
            user=request.user, document=document, access_group_ids=data.validated_data["access_group_ids"], request=request
        )
        return Response(s.DocumentDetailSerializer(_document(request, pk)).data)


class DocumentDownloadView(APIView):
    permission_classes = [HasPerm("documents.view")]

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, pk):
        document = _document(request, pk)
        version = document.current_version
        if number := request.query_params.get("version"):
            version = generics.get_object_or_404(document.versions, version_number=int(number) if number.isdigit() else -1)
        if version is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        audit.record("document.downloaded", actor=request.user, entity_type="document", entity_id=document.pk, request=request,
                     details={"version_number": version.version_number})  # fmt: skip
        response = StreamingHttpResponse(
            storage.stream(version.storage_bucket, version.storage_object_key, version.storage_version_id),
            content_type=document.mime_type,
        )
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(document.filename)}"
        response["Content-Length"] = str(version.file_size)
        response["X-Content-Type-Options"] = "nosniff"
        return response
