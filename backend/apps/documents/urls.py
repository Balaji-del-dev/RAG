from django.urls import path

from . import views

urlpatterns = [
    path("documents/", views.DocumentListView.as_view(), name="documents"),
    path("documents/<uuid:pk>/", views.DocumentDetailView.as_view(), name="document"),
    path("documents/<uuid:pk>/versions/", views.DocumentVersionsView.as_view(), name="document-versions"),
    path("documents/<uuid:pk>/access/", views.DocumentAccessView.as_view(), name="document-access"),
    path("documents/<uuid:pk>/download/", views.DocumentDownloadView.as_view(), name="document-download"),
]
