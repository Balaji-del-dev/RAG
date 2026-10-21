from celery import shared_task

from . import services

RETRY = {
    "autoretry_for": (ConnectionError, TimeoutError, OSError),
    "retry_backoff": 10,
    "retry_backoff_max": 300,
    "max_retries": 5,
}


@shared_task(name="indexing.upsert_version", **RETRY)
def upsert_version(document_version_id: str, pipeline_version_id: str, **_) -> dict:
    return services.index_version(document_version_id, pipeline_version_id)


@shared_task(name="indexing.delete_version", **RETRY)
def delete_version(document_version_id: str, purge_files: bool = False, **_) -> dict:
    return services.remove_version(document_version_id, purge_files)


@shared_task(name="indexing.update_acl", **RETRY)
def update_acl(document_id: str, **_) -> dict:
    return services.update_access(document_id)


@shared_task(name="indexing.build_generation", **RETRY)
def build_generation(build_job_id: str, **_) -> dict:
    return services.run_build(build_job_id)


@shared_task(name="indexing.validate_generation", **RETRY)
def validate_generation(generation_id: str, **_) -> int:
    from .models import IndexGeneration

    return len(services.validate(IndexGeneration.objects.get(pk=generation_id)))


@shared_task(name="indexing.reconcile")
def reconcile() -> dict:
    return services.reconcile()
