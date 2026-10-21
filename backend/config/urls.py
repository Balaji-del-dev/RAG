"""
URL configuration: /api/v1/<app>/… plus the OpenAPI schema and docs.

The Django admin site lives at /django-admin/, so the console's own /admin/… pages
never collide with it. It opens for the Admin role with username and password; when
MFA_REQUIRED_FOR_ADMINS is on it also asks for the authenticator-app code.
"""

from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.admin_site import open_third_party_admins_to_admin_role, site_class

admin.site.__class__ = site_class()
open_third_party_admins_to_admin_role(admin.site)

api_v1 = [
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.registry.urls")),
    path("", include("apps.documents.urls")),
    path("", include("apps.processing.urls")),
    path("", include("apps.indexing.urls")),
    path("", include("apps.retrieval.urls")),
    path("", include("apps.evaluation.urls")),
]

urlpatterns = [
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("django-admin/", admin.site.urls),
]

# uvicorn does not serve static files the way runserver does. In local DEBUG mode Django
# serves them itself (admin CSS); Phase 9 adds whitenoise for daily use.
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
