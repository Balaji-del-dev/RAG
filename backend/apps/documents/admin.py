from django.contrib import messages

from apps.accounts.admin_site import register

from . import services
from .models import Document, DocumentMetadata, DocumentVersion, ExtractedArtifact, StorageObject

FILES_NOT_TOUCHED = (
    "Saved in PostgreSQL only: the files in MinIO and the search indexes were not changed. "
    "Upload, re-process and share documents from the console when you can."
)


class DeleteLikeTheConsole:
    """Deleting a document here does what the console does: hidden at once, then removed from both search
    indexes and from MinIO (index.delete). The row stays, marked DELETED, so the audit trail still points at it."""

    def get_deleted_objects(self, objs, request):
        # Nothing is removed from PostgreSQL, so the versions that protect the row don't block it.
        return [f"{d.filename} (hidden, then removed from search and MinIO)" for d in objs], {"documents": len(objs)}, set(), []

    def delete_model(self, request, obj):
        services.delete_document(user=request.user, document=obj, request=request)
        self.message_user(request, f"{obj.filename} was deleted: it is hidden now and is being removed from search and MinIO.",
                          messages.SUCCESS)  # fmt: skip

    def delete_queryset(self, request, queryset):
        for document in queryset:
            services.delete_document(user=request.user, document=document, request=request)


register(Document, mixins=(DeleteLikeTheConsole,), save_warning=FILES_NOT_TOUCHED)
register(DocumentVersion, DocumentMetadata, ExtractedArtifact, StorageObject, save_warning=FILES_NOT_TOUCHED)
