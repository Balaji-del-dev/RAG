"""Index generations: write both engines, validate, publish or roll back in one PostgreSQL commit."""

import random
import re

import structlog
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.models import DocumentAccessGrant
from apps.core import audit, outbox
from apps.core.clients import search_index, storage, vector_store
from apps.core.exceptions import Conflict
from apps.documents.models import Document, DocumentVersion
from apps.processing.components.store import load_embeddings
from apps.processing.models import Chunk, JobStatus, ProcessingJob
from apps.registry.models import PipelineVersion

from .models import IndexBuildJob, IndexGeneration, IndexMembership, IndexValidation

log = structlog.get_logger(__name__)

OPEN = [IndexGeneration.Status.BUILDING, IndexGeneration.Status.VALIDATING, IndexGeneration.Status.PUBLISHED]
WORD = re.compile(r"[^\W\d_]{5,}", re.UNICODE)
GENERATION_LOCK = 424242
CHECK = IndexValidation.Type


def physical_names(number: int) -> tuple[str, str]:
    prefix = settings.INDEX_NAME_PREFIX
    return f"{prefix}_g{number:04d}", f"{prefix}_v{number:03d}"


def live_generation() -> IndexGeneration | None:
    return IndexGeneration.objects.filter(status=IndexGeneration.Status.PUBLISHED).select_related("pipeline_version").first()


@transaction.atomic
def ensure_generation(pipeline_version: PipelineVersion) -> IndexGeneration:
    """The open generation for a pipeline version, or a new BUILDING one with fresh collection/index names."""
    existing = (
        IndexGeneration.objects.filter(pipeline_version=pipeline_version, status__in=OPEN).order_by("-generation_number").first()
    )
    if existing:
        return existing
    with connection.cursor() as cursor:  # one generation number at a time
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [GENERATION_LOCK])
    existing = IndexGeneration.objects.filter(pipeline_version=pipeline_version, status__in=OPEN).first()
    if existing:
        return existing
    number = (IndexGeneration.objects.aggregate(n=Max("generation_number"))["n"] or 0) + 1
    qdrant_name, opensearch_name = physical_names(number)
    generation = IndexGeneration.objects.create(
        pipeline_version=pipeline_version,
        generation_number=number,
        qdrant_collection=qdrant_name,
        opensearch_index=opensearch_name,
    )
    vector_store.ensure_collection(qdrant_name, 384)
    search_index.ensure_index(opensearch_name)
    log.info("indexing.generation_created", generation=number)
    return generation


def _groups(document_id) -> list[str]:
    return sorted(DocumentAccessGrant.objects.filter(document_id=document_id).values_list("access_group__name", flat=True))


def index_version(document_version_id: str, pipeline_version_id: str) -> dict:
    """Write one document version's chunks to both engines of its pipeline version's generation."""
    version = DocumentVersion.objects.select_related("document").get(pk=document_version_id)
    pipeline_version = PipelineVersion.objects.get(pk=pipeline_version_id)
    if version.status == DocumentVersion.Status.DELETED or version.document.deleted_at:
        return {"skipped": "deleted"}
    generation = ensure_generation(pipeline_version)
    vector_store.ensure_collection(generation.qdrant_collection, 384)
    search_index.ensure_index(generation.opensearch_index)
    chunks = list(Chunk.objects.filter(document_version=version, pipeline_version=pipeline_version).order_by("chunk_index"))
    vectors = load_embeddings(version, pipeline_version)
    missing = [str(c.pk) for c in chunks if str(c.pk) not in vectors]
    if missing:
        raise RuntimeError(f"{len(missing)} chunks have no saved embedding; reprocess the document")
    groups = _groups(version.document_id)
    base = {
        "document_id": str(version.document_id),
        "document_version_id": str(version.pk),
        "index_generation_id": str(generation.pk),
        "access_groups": groups,
    }
    vector_store.upsert(
        generation.qdrant_collection,
        [
            (str(c.pk), vectors[str(c.pk)].tolist(),
             {**base, "chunk_id": str(c.pk), "page_start": c.page_start, "page_end": c.page_end,
              "section_path": c.section_path or "", "content_hash": c.content_hash})
            for c in chunks
        ],
    )  # fmt: skip
    search_index.bulk_upsert(
        generation.opensearch_index,
        [
            {"_id": str(c.pk), **base, "chunk_id": str(c.pk), "content_hash": c.content_hash, "text_content": c.text_content,
             "filename": version.document.filename, "section_path": c.section_path or "",
             "page_start": c.page_start, "page_end": c.page_end}
            for c in chunks
        ],
    )  # fmt: skip

    current_ids = {c.pk for c in chunks}
    stale = IndexMembership.objects.filter(index_generation=generation, document_version=version).exclude(
        chunk_id__in=current_ids
    )
    stale_ids = [str(i) for i in stale.values_list("chunk_id", flat=True)]
    vector_store.delete_ids(generation.qdrant_collection, stale_ids)
    search_index.delete_ids(generation.opensearch_index, stale_ids)

    with transaction.atomic():
        stale.update(status=IndexMembership.Status.REMOVED)
        for c in chunks:
            IndexMembership.objects.update_or_create(
                index_generation=generation,
                chunk=c,
                defaults={
                    "document_version": version,
                    "qdrant_point_id": c.pk,
                    "opensearch_document_id": str(c.pk),
                    "status": IndexMembership.Status.INDEXED,
                },
            )
        generation.refresh_from_db()
        if generation.status == IndexGeneration.Status.PUBLISHED:
            _make_live(version)
        else:
            DocumentVersion.objects.filter(pk=version.pk).update(status=DocumentVersion.Status.VALIDATING_INDEX)
    log.info("indexing.version_indexed", version=str(version.pk), generation=generation.generation_number, chunks=len(chunks))
    return {"generation": generation.generation_number, "chunks": len(chunks), "access_groups": groups}


def _make_live(version: DocumentVersion) -> None:
    """This version is now searchable: it becomes the document's current version; older ones are superseded."""
    DocumentVersion.objects.filter(pk=version.pk).update(status=DocumentVersion.Status.PUBLISHED)
    Document.objects.filter(pk=version.document_id, deleted_at__isnull=True).update(
        current_version=version, lifecycle_status=Document.Lifecycle.ACTIVE, updated_at=timezone.now()
    )
    older = DocumentVersion.objects.filter(document_id=version.document_id, status=DocumentVersion.Status.PUBLISHED).exclude(
        pk=version.pk
    )
    for old in older:
        old.status = DocumentVersion.Status.SUPERSEDED
        old.save(update_fields=["status"])
        outbox.emit("index.delete", old, {"document_version_id": str(old.pk), "purge_files": False})


def remove_version(document_version_id: str, purge_files: bool = False) -> dict:
    version = DocumentVersion.objects.select_related("document").get(pk=document_version_id)
    removed = 0
    generations = IndexGeneration.objects.filter(
        memberships__document_version=version, memberships__status=IndexMembership.Status.INDEXED
    ).distinct()
    for generation in generations:
        vector_store.delete_where(generation.qdrant_collection, "document_version_id", str(version.pk))
        search_index.delete_where(generation.opensearch_index, "document_version_id", str(version.pk))
        removed += IndexMembership.objects.filter(index_generation=generation, document_version=version).update(
            status=IndexMembership.Status.REMOVED
        )
    if purge_files:
        storage.remove_prefix(version.storage_bucket, version.storage_object_key)
        storage.remove_prefix(settings.S3_BUCKET_ARTIFACTS, f"{version.pk}/")
    return {"memberships_removed": removed, "files_purged": purge_files}


def update_access(document_id: str) -> dict:
    groups = _groups(document_id)
    generations = IndexGeneration.objects.filter(
        status__in=OPEN,
        memberships__document_version__document_id=document_id,
        memberships__status=IndexMembership.Status.INDEXED,
    ).distinct()
    for generation in generations:
        vector_store.set_access_groups(generation.qdrant_collection, str(document_id), groups)
        search_index.set_access_groups(generation.opensearch_index, str(document_id), groups)
    return {"generations": len(generations), "access_groups": groups}


# ---------------------------------------------------------------- validation, publish, rollback


def _record(generation, kind, passed, expected=None, actual=None, **details) -> IndexValidation:
    return IndexValidation.objects.create(
        index_generation=generation,
        validation_type=kind,
        status=IndexValidation.Status.PASSED if passed else IndexValidation.Status.FAILED,
        expected_count=expected,
        actual_count=actual,
        details_json=details,
    )


@transaction.atomic
def validate(generation: IndexGeneration) -> list[IndexValidation]:
    """Counts, missing / duplicate / orphaned records and smoke searches, recorded as one validation round.
    A new round replaces the previous one (rows have random UUIDs, so they can't be ordered to find the latest)."""
    generation.validations.all().delete()
    indexed = IndexMembership.objects.filter(index_generation=generation, status=IndexMembership.Status.INDEXED)
    expected_ids = {str(i) for i in indexed.values_list("chunk_id", flat=True)}
    q_ids = vector_store.all_ids(generation.qdrant_collection)
    o_ids = search_index.all_ids(generation.opensearch_index)
    q_count, o_count = len(q_ids), len(o_ids)
    counts_match = len(expected_ids) > 0 and q_count == o_count == len(expected_ids)
    rows = [
        _record(generation, CHECK.COUNT, counts_match, len(expected_ids), q_count,
                qdrant=q_count, opensearch=o_count, note="" if expected_ids else "the generation is empty"),
        _record(generation, CHECK.MISSING, not (expected_ids - q_ids) and not (expected_ids - o_ids), 0,
                len(expected_ids - q_ids) + len(expected_ids - o_ids),
                qdrant=sorted(expected_ids - q_ids)[:20], opensearch=sorted(expected_ids - o_ids)[:20]),
        _record(generation, CHECK.ORPHAN, not (q_ids - expected_ids) and not (o_ids - expected_ids), 0,
                len(q_ids - expected_ids) + len(o_ids - expected_ids),
                qdrant=sorted(q_ids - expected_ids)[:20], opensearch=sorted(o_ids - expected_ids)[:20]),
        _record(generation, CHECK.DUPLICATE, indexed.count() == len(expected_ids), 0, indexed.count() - len(expected_ids)),
    ]  # fmt: skip
    rows += _smoke_tests(generation, expected_ids)
    if all(r.status == IndexValidation.Status.PASSED for r in rows) and generation.status == IndexGeneration.Status.BUILDING:
        generation.status = IndexGeneration.Status.VALIDATING
        generation.save(update_fields=["status"])
    return rows


def _smoke_tests(generation, expected_ids: set[str]) -> list[IndexValidation]:
    """A few chunks must find themselves: by their own vector (dense), by their rarest words (BM25), and in both."""
    sample_ids = random.Random(generation.generation_number).sample(sorted(expected_ids), min(3, len(expected_ids)))  # noqa: S311
    if not sample_ids:
        return [
            _record(generation, kind, False, note="no chunks to search")
            for kind in (CHECK.SMOKE_DENSE, CHECK.SMOKE_LEXICAL, CHECK.SMOKE_HYBRID)
        ]
    dense_hits, lexical_hits = 0, 0
    for chunk in Chunk.objects.filter(pk__in=sample_ids).select_related("document_version", "pipeline_version"):
        groups = _groups(chunk.document_version.document_id) or ["general"]
        vector = load_embeddings(chunk.document_version, chunk.pipeline_version).get(str(chunk.pk))
        if vector is not None:
            found = vector_store.search(
                generation.qdrant_collection, vector.tolist(), generation_id=str(generation.pk), access_groups=groups, limit=3
            )
            dense_hits += any(str(p.id) == str(chunk.pk) for p in found)
        words = sorted(set(WORD.findall(chunk.text_content)), key=len, reverse=True)[:6]
        found = search_index.search(
            generation.opensearch_index, " ".join(words), generation_id=str(generation.pk), access_groups=groups, size=5
        )
        lexical_hits += any(hit["_id"] == str(chunk.pk) for hit in found)
    n = len(sample_ids)
    return [
        _record(generation, CHECK.SMOKE_DENSE, dense_hits == n, n, dense_hits),
        _record(generation, CHECK.SMOKE_LEXICAL, lexical_hits == n, n, lexical_hits),
        _record(generation, CHECK.SMOKE_HYBRID, dense_hits == n and lexical_hits == n, n, min(dense_hits, lexical_hits)),
    ]


def latest_validations(generation: IndexGeneration) -> list[IndexValidation]:
    """The current validation round (validate() keeps only one per generation)."""
    order = {kind: n for n, kind in enumerate(IndexValidation.Type.values)}
    return sorted(generation.validations.all(), key=lambda row: order.get(row.validation_type, len(order)))


def validated(generation: IndexGeneration) -> bool:
    rows = latest_validations(generation)
    return len(rows) == len(IndexValidation.Type) and all(r.status == IndexValidation.Status.PASSED for r in rows)


@transaction.atomic
def publish(generation: IndexGeneration, *, by, request=None, approved_release: bool = False) -> IndexGeneration:
    """Make a validated generation live. Without an approved evaluation run, only the very first one."""
    generation = IndexGeneration.objects.select_for_update().get(pk=generation.pk)
    if generation.status == IndexGeneration.Status.PUBLISHED:
        raise Conflict("This generation is already live.", code="already_published")
    if not validated(generation):
        raise Conflict("Validate the generation first; every check must pass.", code="not_validated")
    current = IndexGeneration.objects.select_for_update().filter(status=IndexGeneration.Status.PUBLISHED).first()
    if current is not None and not approved_release:
        raise Conflict(
            "A generation is already live. New generations are released through evaluation and approval.", code="not_initial"
        )
    if generation.pipeline_version.status != PipelineVersion.Status.PUBLISHED and not approved_release:
        raise Conflict("Publish the pipeline version first.", code="pipeline_not_published")
    if current is not None:
        current.status = IndexGeneration.Status.RETIRED
        current.save(update_fields=["status"])
    generation.status = IndexGeneration.Status.PUBLISHED
    generation.published_at = timezone.now()
    generation.save(update_fields=["status", "published_at"])
    for version in DocumentVersion.objects.filter(
        index_memberships__index_generation=generation,
        index_memberships__status=IndexMembership.Status.INDEXED,
        status__in=[DocumentVersion.Status.VALIDATING_INDEX, DocumentVersion.Status.INDEXING],
    ).distinct():
        _make_live(version)
    audit.record(
        "index_generation.published",
        actor=by,
        entity_type="index_generation",
        entity_id=generation.pk,
        request=request,
        details={"generation": generation.generation_number, "replaced": current.generation_number if current else None},
    )
    return generation


@transaction.atomic
def rollback(generation: IndexGeneration, *, by, request=None) -> IndexGeneration:
    generation = IndexGeneration.objects.select_for_update().get(pk=generation.pk)
    if generation.status != IndexGeneration.Status.RETIRED:
        raise Conflict("Only a retired generation can be made live again.", code="not_retired")
    if not vector_store.client().collection_exists(generation.qdrant_collection):
        raise Conflict("This generation's indexes were already removed.", code="indexes_gone")
    current = IndexGeneration.objects.select_for_update().filter(status=IndexGeneration.Status.PUBLISHED).first()
    if current:
        current.status = IndexGeneration.Status.RETIRED
        current.save(update_fields=["status"])
        if current.pipeline_version_id != generation.pipeline_version_id:
            PipelineVersion.objects.filter(pk=current.pipeline_version_id).update(status=PipelineVersion.Status.RETIRED)
    PipelineVersion.objects.filter(pk=generation.pipeline_version_id).update(status=PipelineVersion.Status.PUBLISHED)
    generation.status = IndexGeneration.Status.PUBLISHED
    generation.published_at = timezone.now()
    generation.save(update_fields=["status", "published_at"])
    audit.record(
        "index_generation.rolled_back",
        actor=by,
        entity_type="index_generation",
        entity_id=generation.pk,
        request=request,
        details={"generation": generation.generation_number, "replaced": current.generation_number if current else None},
    )
    return generation


@transaction.atomic
def start_build(pipeline_version: PipelineVersion, *, by, request=None) -> IndexBuildJob:
    generation = ensure_generation(pipeline_version)
    job = IndexBuildJob.objects.create(index_generation=generation)
    outbox.emit("index.build", job, {"build_job_id": str(job.pk)})
    audit.record(
        "index_generation.build_started", actor=by, entity_type="index_generation", entity_id=generation.pk, request=request
    )
    return job


def run_build(build_job_id: str) -> dict:
    """Fill a generation from every live document: index chunks that exist, reprocess the rest."""
    job = IndexBuildJob.objects.select_related("index_generation__pipeline_version").get(pk=build_job_id)
    IndexBuildJob.objects.filter(pk=job.pk).update(
        status=JobStatus.RUNNING, started_at=timezone.now(), attempt_count=job.attempt_count + 1
    )
    pipeline_version = job.index_generation.pipeline_version
    indexed, queued = 0, 0
    try:
        for document in Document.objects.filter(deleted_at__isnull=True).select_related("current_version"):
            version = document.current_version
            if version is None or version.status == DocumentVersion.Status.DELETED:
                continue
            if Chunk.objects.filter(document_version=version, pipeline_version=pipeline_version).exists():
                index_version(str(version.pk), str(pipeline_version.pk))
                indexed += 1
            elif not ProcessingJob.objects.filter(
                document_version=version, pipeline_version=pipeline_version, status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
            ).exists():
                with transaction.atomic():
                    reprocess = ProcessingJob.objects.create(
                        document_version=version, pipeline_version=pipeline_version, job_type=ProcessingJob.JobType.REPROCESS
                    )
                    outbox.emit("job.dispatch", reprocess, {"job_id": str(reprocess.pk)})
                queued += 1
    except Exception as exc:
        IndexBuildJob.objects.filter(pk=job.pk).update(
            status=JobStatus.FAILED, error_message=str(exc)[:2000], completed_at=timezone.now()
        )
        raise
    IndexBuildJob.objects.filter(pk=job.pk).update(status=JobStatus.SUCCEEDED, completed_at=timezone.now())
    return {"indexed": indexed, "reprocessing": queued}


def reconcile() -> dict:
    """Nightly: re-index versions whose chunks are missing from an engine; remove orphans."""
    report = {}
    for generation in IndexGeneration.objects.filter(status__in=OPEN):
        expected = {
            str(i)
            for i in IndexMembership.objects.filter(index_generation=generation, status="INDEXED").values_list(
                "chunk_id", flat=True
            )
        }
        q_ids = vector_store.all_ids(generation.qdrant_collection)
        o_ids = search_index.all_ids(generation.opensearch_index)
        missing = (expected - q_ids) | (expected - o_ids)
        versions = set(Chunk.objects.filter(pk__in=missing).values_list("document_version_id", "pipeline_version_id"))
        for version_id, pipeline_version_id in versions:
            index_version(str(version_id), str(pipeline_version_id))
        vector_store.delete_ids(generation.qdrant_collection, sorted(q_ids - expected))
        search_index.delete_ids(generation.opensearch_index, sorted(o_ids - expected))
        report[generation.generation_number] = {
            "reindexed_versions": len(versions),
            "orphans_removed": len((q_ids | o_ids) - expected),
        }
    return report
