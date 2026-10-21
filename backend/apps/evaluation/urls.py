from django.urls import path

from . import views

urlpatterns = [
    path("eval/datasets/", views.DatasetListView.as_view(), name="eval-datasets"),
    path("eval/datasets/<uuid:pk>/", views.DatasetDetailView.as_view(), name="eval-dataset"),
    path("eval/datasets/<uuid:pk>/cases/", views.CaseListView.as_view(), name="eval-dataset-cases"),
    path("eval/datasets/<uuid:pk>/import/", views.ImportView.as_view(), name="eval-dataset-import"),
    path("eval/datasets/<uuid:pk>/new-version/", views.NewVersionView.as_view(), name="eval-dataset-new-version"),
    path("eval/datasets/<uuid:pk>/cases/from-failures/", views.FromFailuresView.as_view(), name="eval-dataset-from-failures"),
    path("eval/cases/<uuid:pk>/", views.CaseDetailView.as_view(), name="eval-case"),
    path("eval/candidates/", views.CandidateListView.as_view(), name="eval-candidates"),
    path("eval/runs/", views.RunListView.as_view(), name="eval-runs"),
    path("eval/runs/<uuid:pk>/", views.RunDetailView.as_view(), name="eval-run"),
    path("eval/runs/<uuid:pk>/approve/", views.ApproveView.as_view(), name="eval-run-approve"),
    path("audit-events/", views.AuditEventListView.as_view(), name="audit-events"),
]
