from django.db.models import Prefetch, QuerySet

from apps.accounts.models import DocumentAccessGrant
from apps.accounts.selectors import access_scope

from .models import Document


def visible_documents(user) -> QuerySet[Document]:
    """Documents the user may see: shared with one of their access groups (Admins see all). Never deleted ones."""
    qs = Document.objects.filter(deleted_at__isnull=True)
    if not user.has_perm("accounts.manage"):
        qs = qs.filter(access_grants__access_group__name__in=access_scope(user)).distinct()
    return qs.select_related("current_version", "created_by").prefetch_related(
        Prefetch(
            "access_grants", queryset=DocumentAccessGrant.objects.select_related("access_group").order_by("access_group__name")
        )
    )
