"""Phase 8: datasets, runs (real engines, scripted LLM), gates against the baseline, four-eyes approval."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import AccessGroup, DocumentAccessGrant
from apps.core.clients import llm, search_index, vector_store
from apps.core.exceptions import Conflict
from apps.evaluation import services
from apps.evaluation.models import EvaluationCase, EvaluationDataset
from apps.indexing import services as indexing
from apps.indexing.models import IndexGeneration
from apps.processing import runner
from apps.processing.models import ProcessingJob
from apps.processing.tests.test_pipeline import MARKDOWN, make_job, minio, v1  # noqa: F401
from apps.registry.models import PipelineVersion
from apps.registry.services import clone_version

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(autouse=True)
def drop_test_indexes(db):
    yield
    for generation in IndexGeneration.objects.all():
        vector_store.drop(generation.qdrant_collection)
        search_index.drop(generation.opensearch_index)


@pytest.fixture(autouse=True)
def scripted_llm(monkeypatch):
    def fake_stream(model, prompt, **kwargs):
        question = prompt.rsplit("Question:", 1)[-1]
        yield "Every employee gets 24 days of annual leave per year [1]." if "annual leave" in question else "NO_ANSWER"

    monkeypatch.setattr(llm, "stream", fake_stream)
    monkeypatch.setattr(llm, "complete", lambda model, prompt, **kw: "".join(fake_stream(model, prompt)))


@pytest.fixture
def live(make_user, minio, v1):  # noqa: F811
    job = make_job(make_user, minio, v1, "policy.md", MARKDOWN)
    DocumentAccessGrant.objects.create(
        document=job.document_version.document, access_group=AccessGroup.objects.get(name="general")
    )
    runner.run(str(job.pk))
    indexing.index_version(str(job.document_version_id), str(v1.pk))
    generation = IndexGeneration.objects.get()
    indexing.validate(generation)
    indexing.publish(generation, by=make_user("Release approver"))
    AccessGroup.objects.get_or_create(name="finance")
    return job.document_version


@pytest.fixture
def dataset(db):
    d = EvaluationDataset.objects.create(name="hr-basics")
    EvaluationCase.objects.create(dataset=d, question="How many days of annual leave do I get?", expected_answer="24 days of annual leave",
                                  expected_sources=["policy.md"], case_type="FACTUAL")  # fmt: skip
    EvaluationCase.objects.create(dataset=d, question="What is the parking policy?", case_type="NO_ANSWER")
    EvaluationCase.objects.create(dataset=d, question="How many days of annual leave do I get?", expected_sources=["policy.md"],
                                  case_type="ACCESS", metadata_json={"as_groups": ["finance"]})  # fmt: skip
    return d


def test_a_run_measures_retrieval_answers_abstention_and_access(live, dataset, make_user, v1):  # noqa: F811
    run = services.start_run(dataset=dataset, pipeline_version=v1, generation=IndexGeneration.objects.get(), use_llm_judge=False,
                             by=make_user("Evaluator"))  # fmt: skip
    run = services.execute(str(run.pk))
    metrics = run.summary_json["metrics"]
    assert run.status == "PASSED", run.summary_json
    assert metrics["hit@5"] == 1.0 and metrics["recall@5"] == 1.0 and metrics["mrr"] == 1.0
    assert metrics["answer_keyword_recall"] >= 0.75
    assert metrics["abstention_correct"] == 1.0 and metrics["access_safe"] == 1.0
    assert all(g["passed"] for g in run.summary_json["gates"])


def test_datasets_freeze_once_used_and_get_new_versions(live, dataset, make_user, v1, signed_in):  # noqa: F811
    api, _ = signed_in("Evaluator")
    imported = api.post(f"/api/v1/eval/datasets/{dataset.pk}/import/",
                        {"file": SimpleUploadedFile("cases.csv", b"question,expected_answer,expected_sources,case_type\nWho approves travel?,department head,,FACTUAL\n")},
                        format="multipart")  # fmt: skip
    assert imported.status_code == 201 and imported.json()[0]["question"] == "Who approves travel?"
    run = api.post("/api/v1/eval/runs/", {"dataset_id": str(dataset.pk), "pipeline_version_id": str(v1.pk),
                                          "index_generation_id": str(IndexGeneration.objects.get().pk)}, format="json")  # fmt: skip
    assert run.status_code == 202
    frozen = api.post(
        f"/api/v1/eval/datasets/{dataset.pk}/cases/",
        {"question": "new?", "case_type": "FACTUAL", "expected_sources": []},
        format="json",
    )
    assert frozen.status_code == 409 and frozen.json()["error"]["code"] == "dataset_frozen"
    v2 = api.post(f"/api/v1/eval/datasets/{dataset.pk}/new-version/").json()
    assert v2["version"] == 2 and v2["case_count"] == 4 and v2["frozen"] is False


def test_only_evaluators_start_runs_and_admins_read_the_audit_log(live, dataset, v1, signed_in):  # noqa: F811
    body = {
        "dataset_id": str(dataset.pk),
        "pipeline_version_id": str(v1.pk),
        "index_generation_id": str(IndexGeneration.objects.get().pk),
    }
    assert signed_in("User")[0].post("/api/v1/eval/runs/", body, format="json").status_code == 403
    assert signed_in("Evaluator")[0].post("/api/v1/eval/runs/", body, format="json").status_code == 202
    assert signed_in("Evaluator")[0].get("/api/v1/audit-events/").status_code == 403
    events = signed_in("Admin")[0].get("/api/v1/audit-events/?event_type=evaluation_run").json()["results"]
    assert events and events[0]["event_type"] == "evaluation_run.started"


def test_a_release_needs_a_passed_run_and_a_second_person(live, dataset, make_user, v1):  # noqa: F811
    evaluator = make_user("Evaluator")
    author = make_user("Release approver", "Pipeline engineer")
    other = make_user("Release approver")
    first = IndexGeneration.objects.get()
    baseline = services.execute(
        str(services.start_run(dataset=dataset, pipeline_version=v1, generation=first, use_llm_judge=False, by=evaluator).pk)
    )
    with pytest.raises(Conflict):  # the live version is the baseline: nothing to release
        services.approve(baseline, by=other)

    v2 = clone_version(v1, by=author)
    reprocess = ProcessingJob.objects.create(document_version=live, pipeline_version=v2, job_type="REPROCESS")
    assert runner.run(str(reprocess.pk)) == "SUCCEEDED"
    indexing.index_version(str(live.pk), str(v2.pk))
    second = IndexGeneration.objects.get(pipeline_version=v2)
    indexing.validate(second)
    candidate = services.execute(
        str(services.start_run(dataset=dataset, pipeline_version=v2, generation=second, use_llm_judge=False, by=evaluator).pk)
    )
    assert candidate.status == "PASSED" and candidate.summary_json["baseline_run_id"] == str(baseline.pk)

    with pytest.raises(Conflict) as blocked:
        services.approve(candidate, by=author)
    assert "four-eyes" in str(blocked.value.detail)
    services.approve(candidate, by=other)

    v1.refresh_from_db()
    v2.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()
    assert (v1.status, v2.status) == ("RETIRED", "PUBLISHED") and v2.published_by == other
    assert (first.status, second.status) == ("RETIRED", "PUBLISHED")
    assert PipelineVersion.objects.filter(status="PUBLISHED").count() == 1
