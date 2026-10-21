from django.urls import path

from . import views

urlpatterns = [
    path("index-generations/", views.GenerationListView.as_view(), name="index-generations"),
    path("index-generations/<uuid:pk>/", views.GenerationDetailView.as_view(), name="index-generation"),
    path("index-generations/<uuid:pk>/validate/", views.ValidateView.as_view(), name="index-generation-validate"),
    path("index-generations/<uuid:pk>/publish/", views.PublishView.as_view(), name="index-generation-publish"),
    path("index-generations/<uuid:pk>/rollback/", views.RollbackView.as_view(), name="index-generation-rollback"),
]
