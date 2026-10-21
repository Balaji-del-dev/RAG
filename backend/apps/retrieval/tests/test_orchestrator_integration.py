"""The query path against the real Qdrant, OpenSearch, embedder and reranker; the LLM is scripted."""

import json

import pytest
from django.test import AsyncClient
from rest_framework.test import APIClient

from apps.accounts.models import AccessGroup, DocumentAccessGrant
from apps.core.clients import llm, search_index, vector_store
from apps.indexing import services as indexing
from apps.indexing.models import IndexGeneration
from apps.processing import runner
from apps.processing.tests.test_pipeline import MARKDOWN, make_job, minio, v1  # noqa: F401 — shared fixtures
from apps.retrieval import orchestrator
from apps.retrieval.models import AnswerRecord, FailureCase, RetrievalResult, RetrievalRun
from conftest import PASSWORD

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(autouse=True)
def drop_test_indexes(db):
    yield
    for generation in IndexGeneration.objects.all():
        vector_store.drop(generation.qdrant_collection)
        search_index.drop(generation.opensearch_index)


@pytest.fixture
def live(make_user, minio, v1):  # noqa: F811
    """The leave policy, shared with 'general', processed, indexed and published."""
    job = make_job(make_user, minio, v1, "policy.md", MARKDOWN)
    DocumentAccessGrant.objects.create(
        document=job.document_version.document, access_group=AccessGroup.objects.get(name="general")
    )
    runner.run(str(job.pk))
    indexing.index_version(str(job.document_version_id), str(v1.pk))
    generation = IndexGeneration.objects.get()
    indexing.validate(generation)
    indexing.publish(generation, by=make_user("Release approver"))
    return job.document_version


@pytest.fixture
def scripted(monkeypatch):
    """Replace the LLM: stream() yields the next scripted answer; complete() the next repair."""
    answers: dict[str, list[str]] = {"stream": [], "complete": []}

    def fake_stream(model, prompt, **kwargs):
        text = answers["stream"].pop(0)
        if text == "<down>":
            raise llm.LLMUnavailableError("connection refused")
        yield from [text[: len(text) // 2], text[len(text) // 2 :]]

    monkeypatch.setattr(llm, "stream", fake_stream)
    monkeypatch.setattr(llm, "complete", lambda model, prompt, **kwargs: answers["complete"].pop(0))
    return answers


def ask(user, question):
    events = []
    run = orchestrator.answer(user=user, question=question, emit=lambda name, data: events.append((name, data)))
    return run, events


def test_a_grounded_answer_cites_the_right_chunk(live, make_user, scripted):
    scripted["stream"].append("Every employee gets 24 days of annual leave per year [1].")
    user = make_user()
    run, events = ask(user, "How many days of annual leave do I get?")
    names = [name for name, _ in events]
    assert names[0] == "meta" and "token" in names and names[-1] == "done"
    assert [d["stage"] for n, d in events if n == "status"] == ["searching", "reranking", "writing", "checking"]
    done = events[-1][1]
    assert done["status"] == "VALIDATED" and done["citations"][0]["filename"] == "policy.md"
    cited = done["citations"][0]
    assert "Annual leave" in cited["section_path"]
    run.refresh_from_db()
    assert run.status == "ANSWERED" and run.latency_ms > 0
    assert RetrievalResult.objects.filter(retrieval_run=run).exists()
    assert AnswerRecord.objects.get(retrieval_run=run).citation_data == done["citations"]


def test_a_user_outside_the_group_gets_an_abstention_and_sees_nothing(live, make_user, scripted):
    outsider = make_user(groups=["finance"])
    run, events = ask(outsider, "How many days of annual leave do I get?")
    assert events[-1][0] == "abstain" and events[-1][1]["reason"] == "no_evidence"
    assert not RetrievalResult.objects.filter(retrieval_run=run).exists()  # not even a candidate was found


def test_a_bad_citation_is_repaired_once(live, make_user, scripted):
    scripted["stream"].append("You get 24 days [9].")
    scripted["complete"].append("You get 24 days [1].")
    _, events = ask(make_user(), "How many days of annual leave?")
    assert events[-1][0] == "done" and events[-1][1]["status"] == "REPAIRED"


def test_an_answer_that_stays_unverified_is_not_returned(live, make_user, scripted):
    scripted["stream"].append("You get 24 days.")
    scripted["complete"].append("Still no citation here.")
    run, events = ask(make_user(), "How many days of annual leave?")
    assert events[-1][0] == "abstain" and events[-1][1]["reason"] == "unverified_answer"
    run.refresh_from_db()
    assert run.status == "REJECTED"


def test_no_answer_becomes_an_abstention(live, make_user, scripted):
    scripted["stream"].append("NO_ANSWER")
    _, events = ask(make_user(), "What is the parking policy?")
    assert events[-1][0] == "abstain"


def test_the_llm_being_down_ends_with_an_error(live, make_user, scripted):
    scripted["stream"].append("<down>")
    run, events = ask(make_user(), "How many days of annual leave?")
    assert events[-1] == ("error", {"code": "llm_unavailable", "message": events[-1][1]["message"]})
    run.refresh_from_db()
    assert run.status == "FAILED"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
async def test_the_ask_endpoint_streams_events(live, make_user, scripted):
    from asgiref.sync import sync_to_async

    scripted["stream"].append("Every employee gets 24 days of annual leave per year [1].")
    user = await sync_to_async(make_user)()
    client = AsyncClient()
    await client.aforce_login(user)
    response = await client.post(
        "/api/v1/ask/", json.dumps({"question": "How many days of annual leave?"}), content_type="application/json"
    )
    assert response.status_code == 200 and response["Content-Type"].startswith("text/event-stream")
    body = b"".join([chunk async for chunk in response.streaming_content]).decode()
    assert "event: meta" in body and "event: token" in body and "event: done" in body


def test_ask_needs_sign_in_and_csrf(live, make_user):
    assert APIClient().post("/api/v1/ask/", {"question": "hi"}, format="json").status_code == 401
    user = make_user()
    strict = APIClient(enforce_csrf_checks=True)
    strict.post("/api/v1/auth/login/", {"username": user.username, "password": PASSWORD}, format="json",
                HTTP_X_CSRFTOKEN=strict.get("/api/v1/auth/csrf/").cookies["csrftoken"].value)  # fmt: skip
    assert strict.post("/api/v1/ask/", {"question": "hi"}, format="json").status_code == 403


def test_feedback_and_failure_cases(live, make_user, scripted, signed_in):
    scripted["stream"].append("Every employee gets 24 days of annual leave per year [1].")
    api, user = signed_in()
    run, events = ask(user, "How many days of annual leave?")
    answer_id = events[-1][1]["answer_id"]
    bad = api.post(
        f"/api/v1/answers/{answer_id}/feedback/",
        {"rating": 1, "feedback_text": "wrong", "problem": "NOT_GROUNDED"},
        format="json",
    )
    assert bad.status_code == 200
    case = FailureCase.objects.get(retrieval_run=run)
    assert case.failure_type == "NOT_GROUNDED" and case.review_status == "OPEN"
    reviewer, _ = signed_in("Evaluator")
    listed = reviewer.get("/api/v1/failure-cases/").json()["results"]
    assert listed[0]["question"] == "How many days of annual leave?"
    updated = reviewer.patch(
        f"/api/v1/failure-cases/{case.pk}/", {"review_status": "RESOLVED", "resolution_notes": "ok"}, format="json"
    )
    assert updated.json()["review_status"] == "RESOLVED"
    assert api.get("/api/v1/failure-cases/").status_code == 403
    mine = api.get("/api/v1/runs/?mine=1").json()["results"]
    assert mine[0]["answer"]["my_feedback"]["rating"] == 1
    chunk_id = events[-1][1]["citations"][0]["chunk_id"]
    assert api.get(f"/api/v1/chunks/{chunk_id}/").json()["filename"] == "policy.md"
    assert signed_in(groups=["finance"])[0].get(f"/api/v1/chunks/{chunk_id}/").status_code == 404
    assert RetrievalRun.objects.filter(user=user).count() == 1
