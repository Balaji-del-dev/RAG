"""Steps 9-10: save canonical chunks (deterministic IDs) and embed them (vectors saved as a MinIO artifact)."""

import hashlib
import io
import uuid

import numpy as np
from django.conf import settings
from django.db import transaction

from apps.core.clients import embedder, storage
from apps.documents.models import ArtifactType, ExtractedArtifact
from apps.processing.models import Chunk, ChunkRelationship, EmbeddingRecord
from apps.registry.models import ModelDefinition

from .base import Context, TransientError
from .text import with_header

CHUNK_NAMESPACE = uuid.UUID("6f6e0d3e-8a1b-4c63-9b70-0a6c5e3f9d21")


def chunk_id(version_id, pipeline_version_id, index: int, content_hash: str) -> uuid.UUID:
    """Same inputs, same ID: retries never duplicate a chunk in PostgreSQL, Qdrant or OpenSearch."""
    return uuid.uuid5(CHUNK_NAMESPACE, f"{version_id}·{pipeline_version_id}·{index}·{content_hash}")


def chunk_persist(ctx: Context, config: dict) -> dict:
    version, pipeline_version = ctx.version, ctx.pipeline_version
    for index, chunk in enumerate(ctx.chunks):
        chunk.id = chunk_id(version.pk, pipeline_version.pk, index, chunk.content_hash)
    ids = [c.id for c in ctx.chunks]
    with transaction.atomic():
        stale = Chunk.objects.filter(document_version=version, pipeline_version=pipeline_version).exclude(pk__in=ids)
        stale_ids = list(stale.filter(index_memberships__isnull=True).values_list("pk", flat=True))
        ChunkRelationship.objects.filter(source_chunk_id__in=stale_ids).delete()
        EmbeddingRecord.objects.filter(chunk_id__in=stale_ids).delete()
        Chunk.objects.filter(pk__in=stale_ids).delete()
        Chunk.objects.bulk_create(
            [
                Chunk(
                    id=c.id,
                    document_version=version,
                    pipeline_version=pipeline_version,
                    chunk_index=index,
                    text_content=c.text,
                    token_count=c.token_count,
                    page_start=c.page_start,
                    page_end=c.page_end if (c.page_end or 0) >= (c.page_start or 0) else c.page_start,
                    section_path=c.section_path or None,
                    content_hash=c.content_hash,
                    metadata_json={"kind": c.kind, "table_group": c.table_group},
                )
                for index, c in enumerate(ctx.chunks)
            ],
            ignore_conflicts=True,
        )
        relationships = [
            ChunkRelationship(source_chunk_id=a.id, target_chunk_id=b.id, relationship_type="NEXT")
            for a, b in zip(ctx.chunks, ctx.chunks[1:], strict=False)
        ] + [
            ChunkRelationship(source_chunk_id=a.id, target_chunk_id=b.id, relationship_type="SAME_TABLE")
            for a, b in zip(ctx.chunks, ctx.chunks[1:], strict=False)
            if a.table_group is not None and a.table_group == b.table_group
        ]
        ChunkRelationship.objects.bulk_create(relationships, ignore_conflicts=True)
    return {"chunks": len(ids), "relationships": len(relationships), "stale_removed": len(stale_ids)}


def _embedding_key(ctx: Context) -> str:
    return f"{ctx.version.pk}/{ctx.pipeline_version.pk}/embeddings.npz"


def embed_sentence_transformers(ctx: Context, config: dict) -> dict:
    model_def = ModelDefinition.objects.get(name="multilingual-e5-small")
    model_version = embedder.model_version()
    ids = [str(c.id) for c in ctx.chunks]
    key = _embedding_key(ctx)
    existing = ExtractedArtifact.objects.filter(
        document_version=ctx.version, artifact_type=ArtifactType.EMBEDDINGS, storage_object_key=key
    ).first()
    if (
        existing
        and existing.metadata_json.get("chunk_ids") == ids
        and existing.metadata_json.get("model_version") == model_version
        and existing.metadata_json.get("contextual", False) == bool(config.get("contextual"))
    ):
        return {"skipped": True, "reason": "embeddings already saved for these chunks", "vectors": len(ids)}

    filename = ctx.version.document.filename
    texts = [
        with_header(c.text, filename=filename, section_path=c.section_path) if config.get("contextual") else c.text
        for c in ctx.chunks
    ]
    vectors = embedder.embed_passages(
        texts,
        prefix=config.get("passage_prefix", "passage: "),
        batch_size=int(config.get("batch_size", 16)),
        normalize=bool(config.get("normalize", True)),
    )
    buffer = io.BytesIO()
    np.savez_compressed(buffer, vectors=vectors, ids=np.array(ids))
    data = buffer.getvalue()
    try:
        storage.put_bytes(settings.S3_BUCKET_ARTIFACTS, key, data)
    except Exception as exc:
        raise TransientError(f"could not save embeddings to MinIO: {exc}") from exc

    with transaction.atomic():
        ExtractedArtifact.objects.update_or_create(
            document_version=ctx.version,
            artifact_type=ArtifactType.EMBEDDINGS,
            storage_object_key=key,
            defaults={
                "storage_bucket": settings.S3_BUCKET_ARTIFACTS,
                "content_sha256": hashlib.sha256(data).hexdigest(),
                "metadata_json": {
                    "chunk_ids": ids,
                    "model_version": model_version,
                    "dimension": int(vectors.shape[1]),
                    "pipeline_version_id": str(ctx.pipeline_version.pk),
                    "contextual": bool(config.get("contextual")),
                },
            },
        )
        EmbeddingRecord.objects.bulk_create(
            [
                EmbeddingRecord(
                    chunk_id=c.id,
                    model=model_def,
                    model_version=model_version,
                    vector_dimension=int(vectors.shape[1]),
                    vector_point_id=c.id,
                    content_hash=c.content_hash,
                    status=EmbeddingRecord.Status.EMBEDDED,
                )
                for c in ctx.chunks
            ],
            ignore_conflicts=True,
        )
    return {"vectors": len(ids), "dimension": int(vectors.shape[1]), "model_version": model_version, "bytes": len(data)}


def load_embeddings(document_version, pipeline_version) -> dict[str, np.ndarray]:
    """chunk_id -> vector, from the artifact saved in step 10."""
    key = f"{document_version.pk}/{pipeline_version.pk}/embeddings.npz"
    artifact = ExtractedArtifact.objects.filter(
        document_version=document_version, artifact_type=ArtifactType.EMBEDDINGS, storage_object_key=key
    ).first()
    if artifact is None:
        return {}
    data = np.load(io.BytesIO(storage.read_bytes(artifact.storage_bucket, artifact.storage_object_key)))
    return {str(chunk): vector for chunk, vector in zip(data["ids"], data["vectors"], strict=True)}
