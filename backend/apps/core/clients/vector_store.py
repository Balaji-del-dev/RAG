"""Qdrant: one collection per index generation; point ID = chunk ID; access_groups is a mandatory filter."""

from functools import lru_cache

from django.conf import settings
from qdrant_client import QdrantClient
from qdrant_client import models as qm

from . import http

KEYWORD_FIELDS = ("chunk_id", "document_id", "document_version_id", "index_generation_id", "access_groups")


def _headers() -> dict[str, str]:
    return {"api-key": settings.QDRANT_API_KEY} if settings.QDRANT_API_KEY else {}


def ping() -> bool:
    return http.get(f"{settings.QDRANT_URL}/readyz", headers=_headers()).status_code == 200


@lru_cache(maxsize=1)
def client() -> QdrantClient:
    # The local server is 1.17.x; the 1.19 client works with it but warns, so the version check is off.
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None, timeout=60, check_compatibility=False)


def ensure_collection(name: str, dimension: int) -> None:
    if client().collection_exists(name):
        return
    client().create_collection(
        name,
        vectors_config=qm.VectorParams(size=dimension, distance=qm.Distance.COSINE),
        hnsw_config=qm.HnswConfigDiff(m=16, ef_construct=100),
        on_disk_payload=True,
    )
    for field in KEYWORD_FIELDS:
        client().create_payload_index(name, field, field_schema=qm.PayloadSchemaType.KEYWORD, wait=True)
    client().create_payload_index(name, "page_start", field_schema=qm.PayloadSchemaType.INTEGER, wait=True)


def _match(field: str, value: str) -> qm.FieldCondition:
    return qm.FieldCondition(key=field, match=qm.MatchValue(value=value))


def upsert(name: str, points: list[tuple[str, list[float], dict]]) -> None:
    for start in range(0, len(points), 256):
        batch = points[start : start + 256]
        client().upsert(
            name, points=[qm.PointStruct(id=pid, vector=vec, payload=payload) for pid, vec, payload in batch], wait=True
        )


def delete_where(name: str, field: str, value: str) -> None:
    client().delete(name, points_selector=qm.FilterSelector(filter=qm.Filter(must=[_match(field, value)])), wait=True)


def delete_ids(name: str, ids: list[str]) -> None:
    if ids:
        client().delete(name, points_selector=qm.PointIdsList(points=ids), wait=True)


def set_access_groups(name: str, document_id: str, groups: list[str]) -> None:
    client().set_payload(
        name, payload={"access_groups": groups}, points=qm.Filter(must=[_match("document_id", document_id)]), wait=True
    )


def count(name: str) -> int:
    return client().count(name, exact=True).count


def all_ids(name: str) -> set[str]:
    ids: set[str] = set()
    offset = None
    while True:
        points, offset = client().scroll(name, limit=1000, offset=offset, with_payload=False, with_vectors=False)
        ids.update(str(p.id) for p in points)
        if offset is None:
            return ids


def search(name: str, vector: list[float], *, generation_id: str, access_groups: list[str], limit: int) -> list:
    """Dense search; the generation and the user's access groups are always in the filter."""
    if not access_groups:
        return []
    query_filter = qm.Filter(
        must=[
            _match("index_generation_id", generation_id),
            qm.FieldCondition(key="access_groups", match=qm.MatchAny(any=access_groups)),
        ]
    )
    return client().query_points(name, query=vector, query_filter=query_filter, limit=limit, with_payload=True).points


def drop(name: str) -> None:
    if client().collection_exists(name):
        client().delete_collection(name)
