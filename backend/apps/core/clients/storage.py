"""MinIO through the S3 API, with the bucket-limited app user (never the root login)."""

from collections.abc import Iterator
from functools import lru_cache
from urllib.parse import urlparse

from django.conf import settings
from minio import Minio

from . import http


@lru_cache(maxsize=1)
def client() -> Minio:
    endpoint = urlparse(settings.S3_ENDPOINT_URL)
    return Minio(
        endpoint.netloc,
        access_key=settings.S3_ACCESS_KEY,
        secret_key=settings.S3_SECRET_KEY,
        secure=endpoint.scheme == "https",
    )


def ping() -> bool:
    return http.get(f"{settings.S3_ENDPOINT_URL}/minio/health/live").status_code == 200


def put_file(bucket: str, key: str, path: str, content_type: str, metadata: dict | None = None) -> str | None:
    """Upload a local file; returns the object's version ID (buckets are versioned)."""
    result = client().fput_object(bucket, key, path, content_type=content_type, metadata=metadata or {})
    return result.version_id


def put_bytes(bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> str | None:
    import io

    result = client().put_object(bucket, key, io.BytesIO(data), len(data), content_type=content_type)
    return result.version_id


def read_bytes(bucket: str, key: str, version_id: str | None = None) -> bytes:
    response = client().get_object(bucket, key, version_id=version_id)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def download_to(bucket: str, key: str, path: str, version_id: str | None = None) -> None:
    client().fget_object(bucket, key, path, version_id=version_id)


def stream(bucket: str, key: str, version_id: str | None = None, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    response = client().get_object(bucket, key, version_id=version_id)
    try:
        yield from response.stream(chunk_size)
    finally:
        response.close()
        response.release_conn()


def remove_prefix(bucket: str, prefix: str) -> int:
    """Delete every object version under a prefix. Returns how many versions were removed."""
    from minio.deleteobjects import DeleteObject

    targets = [
        DeleteObject(obj.object_name, version_id=obj.version_id)
        for obj in client().list_objects(bucket, prefix=prefix, recursive=True, include_version=True)
    ]
    if not targets:
        return 0
    errors = list(client().remove_objects(bucket, targets))
    if errors:
        raise RuntimeError(f"could not delete {len(errors)} objects under {bucket}/{prefix}: {errors[0]}")
    return len(targets)
