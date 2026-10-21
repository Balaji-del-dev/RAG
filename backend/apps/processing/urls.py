from django.urls import path

from . import views

urlpatterns = [
    path("jobs/", views.JobListView.as_view(), name="jobs"),
    path("jobs/<uuid:pk>/", views.JobDetailView.as_view(), name="job"),
    path("jobs/<uuid:pk>/retry/", views.JobRetryView.as_view(), name="job-retry"),
    path("jobs/<uuid:pk>/cancel/", views.JobCancelView.as_view(), name="job-cancel"),
]
