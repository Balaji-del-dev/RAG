from django.urls import path

from . import ask, views

urlpatterns = [
    path("ask/", ask.ask, name="ask"),
    path("runs/", views.RunListView.as_view(), name="runs"),
    path("runs/<uuid:pk>/", views.RunDetailView.as_view(), name="run"),
    path("chunks/<uuid:pk>/", views.ChunkView.as_view(), name="chunk"),
    path("answers/<uuid:pk>/feedback/", views.FeedbackView.as_view(), name="answer-feedback"),
    path("failure-cases/", views.FailureCaseListView.as_view(), name="failure-cases"),
    path("failure-cases/<uuid:pk>/", views.FailureCaseDetailView.as_view(), name="failure-case"),
]
