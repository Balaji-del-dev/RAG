from django.urls import path

from . import views

urlpatterns = [
    path("pipelines/", views.PipelineListView.as_view(), name="pipelines"),
    path("pipeline-versions/<uuid:pk>/", views.PipelineVersionView.as_view(), name="pipeline-version"),
    path("pipeline-versions/<uuid:pk>/clone/", views.CloneVersionView.as_view(), name="pipeline-version-clone"),
    path("pipeline-versions/<uuid:pk>/steps/", views.StepsView.as_view(), name="pipeline-version-steps"),
    path(
        "pipeline-versions/<uuid:pk>/publish-initial/",
        views.PublishInitialView.as_view(),
        name="pipeline-version-publish-initial",
    ),
    path("components/", views.ComponentListView.as_view(), name="components"),
    path("models/", views.ModelListView.as_view(), name="models"),
    path("retrieval-definitions/", views.RetrievalDefinitionListView.as_view(), name="retrieval-definitions"),
    path("retrieval-definitions/<uuid:pk>/", views.RetrievalDefinitionDetailView.as_view(), name="retrieval-definition"),
    path("generation-definitions/", views.GenerationDefinitionListView.as_view(), name="generation-definitions"),
    path("generation-definitions/<uuid:pk>/", views.GenerationDefinitionDetailView.as_view(), name="generation-definition"),
]
