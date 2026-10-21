"""Pipeline v2 settings against the real Qdrant, OpenSearch, embedder and reranker; the LLM is scripted."""

import pytest

from apps.accounts.models import AccessGroup, DocumentAccessGrant
from apps.core.clients import llm, search_index, vector_store
from apps.indexing import services as indexing
from apps.indexing.models import IndexGeneration
from apps.processing import runner
from apps.processing.tests.test_pipeline import make_job, minio, v1  # noqa: F401 — shared fixtures
from apps.registry import services as registry
from apps.registry.components import CONTEXTUAL_RETRIEVAL_V2, GENERATION_V2, GROUNDED_PROMPT_V2
from apps.retrieval import orchestrator

pytestmark = [pytest.mark.integration, pytest.mark.slow]

# The person's name is only in the file name: the experience section never says it.
RESUME = b"""Senior Python Developer | Chennai | asha@example.org

## PROFESSIONAL EXPERIENCE
Acme Corp - Software Engineer (2021 - Present)
- Built a document search service with Django, PostgreSQL and OpenSearch.
- Led a team of four engineers and mentored two interns.

## LANGUAGES
English (fluent), Tamil (native)
"""


@pytest.fixture(autouse=True)
def drop_test_indexes(db):
    yield
    for generation in IndexGeneration.objects.all():
        vector_store.drop(generation.qdrant_collection)
        search_index.drop(generation.opensearch_index)


@pytest.fixture
def v2_live(make_user, minio, v1):  # noqa: F811
    engineer = make_user("Pipeline engineer")
    v2 = registry.clone_version(v1, by=engineer)
    steps = [
        {"component": s.component.name, "config": {**s.config_json, "contextual": s.component.name.startswith("embed.")}
         if s.component.name.startswith("embed.") else s.config_json, "is_enabled": s.is_enabled}
        for s in v1.steps.select_related("component").order_by("step_order")
    ]  # fmt: skip
    registry.replace_steps(v2, steps, by=engineer)
    retrieval = registry.save_retrieval_definition(None, name="test-v2", configs=CONTEXTUAL_RETRIEVAL_V2, by=engineer)
    generation = registry.save_generation_definition(
        None, name="test-grounded-v2", model=v1.generation_definition.model, prompt_template=GROUNDED_PROMPT_V2,
        configs=GENERATION_V2, by=engineer,
    )  # fmt: skip
    registry.update_draft(v2, by=engineer, retrieval_definition=retrieval, generation_definition=generation)
    job = make_job(make_user, minio, v2, "Asha_Raman_Resume.md", RESUME)
    DocumentAccessGrant.objects.create(
        document=job.document_version.document, access_group=AccessGroup.objects.get(name="general")
    )
    assert runner.run(str(job.pk)) == "SUCCEEDED"
    indexing.index_version(str(job.document_version_id), str(v2.pk))
    live = IndexGeneration.objects.get(pipeline_version=v2)
    indexing.validate(live)
    indexing.publish(live, by=make_user("Release approver"), approved_release=True)
    return v2


def ask(user, question, prompts):
    context, events = [], []
    orchestrator.answer(user=user, question=question, emit=lambda n, d: events.append((n, d)), on_context=context.extend)
    return [c.chunk.section_path for c in context], events


@pytest.mark.parametrize(
    "question",
    ["asha raman experience", "asha raman expirience", "Tell me about Asha's work", "give me a details summery of asha"],
)
def test_a_section_is_found_by_the_name_in_its_file_title(v2_live, make_user, monkeypatch, question):
    prompts = []

    def fake_stream(model, prompt, **kwargs):
        prompts.append((prompt, kwargs))
        yield "Asha built a document search service with Django [1]."

    monkeypatch.setattr(llm, "stream", fake_stream)
    sections, events = ask(make_user(), question, prompts)
    assert "PROFESSIONAL EXPERIENCE" in sections
    prompt, kwargs = prompts[0]
    assert "section: PROFESSIONAL EXPERIENCE" in prompt and "Example of the expected style" in prompt
    assert kwargs["num_ctx"] == 4096 and kwargs["max_tokens"] == 600
    assert events[-1][0] == "done"


def test_an_unrelated_question_still_finds_nothing(v2_live, make_user, monkeypatch):
    monkeypatch.setattr(llm, "stream", lambda *a, **k: pytest.fail("nothing relevant: the model must not be asked"))
    sections, events = ask(make_user(), "What is the company parking policy?", [])
    assert sections == [] and events[-1][1]["reason"] == "no_evidence"
