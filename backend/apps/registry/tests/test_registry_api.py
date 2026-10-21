import pytest

from apps.registry.components import BASELINE_STEPS, COMPONENTS
from apps.registry.models import ComponentDefinition, PipelineVersion, RetrievalDefinition


@pytest.fixture
def v1(db):
    return PipelineVersion.objects.get(pipeline__name="default", version_number=1)


def steps_payload(version):
    return [
        {"component": s.component.name, "config": s.config_json, "is_enabled": s.is_enabled}
        for s in version.steps.order_by("step_order")
    ]


def test_seed_has_the_baseline_pipeline_and_every_component(v1):
    assert v1.status == "DRAFT"
    assert [s.component.name for s in v1.steps.order_by("step_order")] == BASELINE_STEPS
    assert set(ComponentDefinition.objects.values_list("name", flat=True)) == set(COMPONENTS)
    assert v1.retrieval_definition.name == "baseline" and v1.generation_definition.name == "grounded-v1"


@pytest.mark.parametrize(
    ("role", "code"), [("User", 403), ("Pipeline engineer", 200), ("Evaluator", 200), ("Release approver", 200)]
)
def test_who_may_see_pipelines(signed_in, v1, role, code):
    api, _ = signed_in(role)
    assert api.get("/api/v1/pipelines/").status_code == code
    assert api.get(f"/api/v1/pipeline-versions/{v1.pk}/").status_code == code


def test_only_pipeline_engineers_edit(signed_in, v1):
    api, _ = signed_in("Evaluator")
    assert api.patch(f"/api/v1/pipeline-versions/{v1.pk}/", {"config_json": {}}, format="json").status_code == 403
    assert api.post(f"/api/v1/pipeline-versions/{v1.pk}/clone/").status_code == 403


def test_clone_makes_a_new_draft_with_the_same_steps_and_an_author(signed_in, v1):
    api, user = signed_in("Pipeline engineer")
    response = api.post(f"/api/v1/pipeline-versions/{v1.pk}/clone/")
    assert response.status_code == 201
    body = response.json()
    assert body["version_number"] == 2 and body["status"] == "DRAFT" and body["created_by"] == user.username
    assert [s["component"] for s in body["steps"]] == BASELINE_STEPS


def test_edit_a_draft_and_replace_its_steps(signed_in, v1):
    api, _ = signed_in("Pipeline engineer")
    steps = steps_payload(v1)
    steps[6]["config"]["max_tokens"] = 300
    steps[5]["is_enabled"] = False
    response = api.put(f"/api/v1/pipeline-versions/{v1.pk}/steps/", {"steps": steps}, format="json")
    assert response.status_code == 200, response.json()
    assert response.json()["steps"][6]["config"]["max_tokens"] == 300
    assert response.json()["steps"][5]["is_enabled"] is False


@pytest.mark.parametrize(
    ("change", "field"),
    [
        (lambda steps: steps[6]["config"].update(max_tokens=9999), "steps.6.config.max_tokens"),
        (lambda steps: steps[6]["config"].update(surprise=True), "steps.6.config.surprise"),
        (lambda steps: steps[0].update(component="os.system"), "steps.0.component"),
        (lambda steps: steps[0].update(component="retrieve.qdrant_dense"), "steps.0.component"),
    ],
    ids=["out-of-range", "unknown-setting", "not-on-allow-list", "not-an-ingestion-step"],
)
def test_bad_steps_are_refused_with_field_errors(signed_in, v1, change, field):
    api, _ = signed_in("Pipeline engineer")
    steps = steps_payload(v1)
    change(steps)
    response = api.put(f"/api/v1/pipeline-versions/{v1.pk}/steps/", {"steps": steps}, format="json")
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


def test_publish_initial_then_the_version_is_frozen(signed_in, v1):
    engineer, _ = signed_in("Pipeline engineer")
    approver, approver_user = signed_in("Release approver")
    assert engineer.post(f"/api/v1/pipeline-versions/{v1.pk}/publish-initial/").status_code == 403
    response = approver.post(f"/api/v1/pipeline-versions/{v1.pk}/publish-initial/")
    assert response.status_code == 200
    assert response.json()["status"] == "PUBLISHED" and response.json()["published_by"] == approver_user.username

    frozen = engineer.patch(f"/api/v1/pipeline-versions/{v1.pk}/", {"config_json": {"x": 1}}, format="json")
    assert frozen.status_code == 409 and frozen.json()["error"]["code"] == "version_published"

    v2 = engineer.post(f"/api/v1/pipeline-versions/{v1.pk}/clone/").json()
    again = approver.post(f"/api/v1/pipeline-versions/{v2['id']}/publish-initial/")
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_initial"


def test_retrieval_settings_are_validated_and_frozen_once_used(signed_in, v1):
    engineer, _ = signed_in("Pipeline engineer")
    approver, _ = signed_in("Release approver")
    bad = engineer.post("/api/v1/retrieval-definitions/", {"name": "wide", "dense_config": {"top_k": 0}}, format="json")
    assert bad.status_code == 400 and "dense_config.top_k" in bad.json()["error"]["details"]
    good = engineer.post("/api/v1/retrieval-definitions/", {"name": "wide", "dense_config": {"top_k": 40}}, format="json")
    assert good.status_code == 201 and good.json()["dense_config"]["top_k"] == 40

    approver.post(f"/api/v1/pipeline-versions/{v1.pk}/publish-initial/")
    baseline = RetrievalDefinition.objects.get(name="baseline")
    used = engineer.patch(f"/api/v1/retrieval-definitions/{baseline.pk}/", {"fusion_config": {"k": 10}}, format="json")
    assert used.status_code == 409 and used.json()["error"]["code"] == "definition_in_use"


def test_generation_prompt_needs_its_placeholders(signed_in, v1):
    api, _ = signed_in("Pipeline engineer")
    model_id = str(v1.generation_definition.model_id)
    response = api.post(
        "/api/v1/generation-definitions/",
        {"name": "short", "model_id": model_id, "prompt_template": "Answer: {question}"},
        format="json",
    )
    assert response.status_code == 400 and "prompt_template" in response.json()["error"]["details"]


def test_components_list_their_config_schema(signed_in):
    api, _ = signed_in("Pipeline engineer")
    components = {c["key"]: c for c in api.get("/api/v1/components/").json()}
    assert components["chunk.structure_aware"]["config_schema"]["properties"]["max_tokens"]["maximum"] == 480
