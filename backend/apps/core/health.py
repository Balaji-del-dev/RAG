"""Up / down checks for every backing service. Reports nothing beyond up or down."""

from collections.abc import Callable

import redis
import structlog
from django.conf import settings
from django.db import connection

from .clients import llm, search_index, storage, vector_store

log = structlog.get_logger(__name__)


def _postgres() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        return cursor.fetchone() == (1,)


def _redis() -> bool:
    client = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=settings.HEALTH_CHECK_TIMEOUT)
    return bool(client.ping())


CHECKS: dict[str, Callable[[], bool]] = {
    "postgres": _postgres,
    "redis": _redis,
    "minio": storage.ping,
    "qdrant": vector_store.ping,
    "opensearch": search_index.ping,
    "ollama": llm.ping,
}


def check_all() -> dict[str, str]:
    results = {}
    for name, check in CHECKS.items():
        try:
            results[name] = "up" if check() else "down"
        except Exception as exc:
            log.warning("health.check_failed", service=name, error=str(exc))
            results[name] = "down"
    return results
