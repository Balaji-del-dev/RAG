"""Phase 6 against the real local Qdrant and OpenSearch (test-only index names, dropped afterwards)."""

import pytest

from apps.accounts.models import AccessGroup, DocumentAccessGrant
from apps.core.clients import embedder, search_index, vector_store
from apps.core.exceptions import Conflict
from apps.documents.models import DocumentVersion
from apps.indexing import services
from apps.indexing.models import IndexGeneration, IndexMembership, IndexValidation
from apps.processing import runner
from apps.processing.models import Chunk
from apps.processing.tests.test_pipeline import MARKDOWN, make_job, minio, v1  # noqa: F401 — shared fixtures

pytestmark = [pytest.mark.integration, pytest.mark.slow]


@pytest.fixture(autouse=True)
def drop_test_indexes(db):
    yield
    for generation in IndexGeneration.objects.all():
        vector_store.drop(generation.qdrant_collection)
        search_index.drop(generation.opensearch_index)


@pytest.fixture
def indexed(make_user, minio, v1):  # noqa: F811
    """A processed Markdown document, shared with the 'finance' group only, indexed into a BUILDING generation."""
    job = make_job(make_user, minio, v1, "policy.md", MARKDOWN)
    version = job.document_version
    finance = AccessGroup.objects.create(name="finance")
    DocumentAccessGrant.objects.create(document=version.document, access_group=finance)
    assert runner.run(str(job.pk)) == "SUCCEEDED"
    services.index_version(str(version.pk), str(v1.pk))
    return version


def dense_hits(generation, groups, text="How many days of annual leave?"):
    vector = embedder.embed_query(text).tolist()
    return vector_store.search(
        generation.qdrant_collection, vector, generation_id=str(generation.pk), access_groups=groups, limit=5
    )


def lexical_hits(generation, groups, text="annual leave days"):
    return search_index.search(generation.opensearch_index, text, generation_id=str(generation.pk), access_groups=groups, size=5)


def test_both_engines_get_every_chunk_and_upserts_are_idempotent(indexed, v1):  # noqa: F811
    generation = IndexGeneration.objects.get()
    chunks = Chunk.objects.filter(document_version=indexed).count()
    assert generation.status == "BUILDING" and generation.qdrant_collection.endswith("_g0001")
    assert vector_store.count(generation.qdrant_collection) == search_index.count(generation.opensearch_index) == chunks
    services.index_version(str(indexed.pk), str(v1.pk))
    assert vector_store.count(generation.qdrant_collection) == search_index.count(generation.opensearch_index) == chunks
    indexed.refresh_from_db()
    assert indexed.status == "VALIDATING_INDEX"


def test_access_groups_filter_both_engines(indexed):
    generation = IndexGeneration.objects.get()
    assert dense_hits(generation, ["general"]) == [] and lexical_hits(generation, ["general"]) == []
    assert dense_hits(generation, ["finance"]) and lexical_hits(generation, ["finance"])

    general = AccessGroup.objects.get(name="general")
    DocumentAccessGrant.objects.filter(document=indexed.document).update(access_group=general)
    services.update_access(str(indexed.document_id))
    assert dense_hits(generation, ["general"]) and lexical_hits(generation, ["general"])
    assert dense_hits(generation, ["finance"]) == [] and lexical_hits(generation, ["finance"]) == []


def test_validate_then_publish_makes_the_document_live(indexed, make_user):
    generation = IndexGeneration.objects.get()
    rows = services.validate(generation)
    assert {r.validation_type: r.status for r in rows} == dict.fromkeys(
        ["COUNT", "MISSING", "ORPHAN", "DUPLICATE", "SMOKE_DENSE", "SMOKE_LEXICAL", "SMOKE_HYBRID"], "PASSED"
    )
    generation.refresh_from_db()
    assert generation.status == "VALIDATING"
    services.publish(generation, by=make_user("Release approver"))
    generation.refresh_from_db()
    indexed.refresh_from_db()
    assert generation.status == "PUBLISHED"
    assert indexed.status == "PUBLISHED" and indexed.document.lifecycle_status == "ACTIVE"


def test_a_chunk_missing_from_one_engine_blocks_publishing_and_reconcile_repairs_it(indexed, make_user):
    generation = IndexGeneration.objects.get()
    one = str(Chunk.objects.filter(document_version=indexed).first().pk)
    search_index.delete_ids(generation.opensearch_index, [one])
    rows = {r.validation_type: r for r in services.validate(generation)}
    assert rows["MISSING"].status == "FAILED" and one in rows["MISSING"].details_json["opensearch"]
    with pytest.raises(Conflict):
        services.publish(generation, by=make_user("Release approver"))
    services.reconcile()
    assert all(r.status == "PASSED" for r in services.validate(generation))
    # The failed round is replaced, not mixed in: publishing is allowed now.
    assert services.validated(generation) and generation.validations.count() == len(IndexValidation.Type)


def test_deleting_removes_the_version_from_both_engines(indexed):
    generation = IndexGeneration.objects.get()
    services.remove_version(str(indexed.pk))
    assert vector_store.count(generation.qdrant_collection) == 0 and search_index.count(generation.opensearch_index) == 0
    assert set(IndexMembership.objects.values_list("status", flat=True)) == {"REMOVED"}


def test_the_second_generation_needs_an_approved_release(indexed, make_user, v1):  # noqa: F811
    approver = make_user("Release approver")
    first = IndexGeneration.objects.get()
    services.validate(first)
    services.publish(first, by=approver)
    from apps.registry.services import clone_version

    v2 = clone_version(v1, by=make_user("Pipeline engineer"))
    second = services.ensure_generation(v2)
    assert second.generation_number == 2
    DocumentVersion.objects.filter(pk=indexed.pk).update(status="INDEXING")
    with pytest.raises(Conflict):
        services.publish(second, by=approver)
