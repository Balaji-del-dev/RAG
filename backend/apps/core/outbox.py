"""Transactional outbox: emit() inside the caller's transaction, dispatch_batch() from run_outbox."""

import uuid
from datetime import timedelta

import structlog
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from config.celery import app as celery_app

from .models import OutboxEvent

log = structlog.get_logger(__name__)

# event type -> Celery task name (the queue comes from CELERY_TASK_ROUTES)
EVENT_TASKS = {
    "core.ping": "core.ping",
    "job.dispatch": "processing.run_job",
    "index.upsert": "indexing.upsert_version",
    "index.delete": "indexing.delete_version",
    "index.acl": "indexing.update_acl",
    "index.build": "indexing.build_generation",
    "index.validate": "indexing.validate_generation",
    "evaluation.run": "evaluation.run_evaluation",
}


def emit(event_type: str, aggregate: models.Model, payload: dict | None = None) -> OutboxEvent:
    """Record an event. Call inside the same transaction as the change it announces."""
    if event_type not in EVENT_TASKS:
        raise ValueError(f"unknown outbox event type: {event_type}")
    aggregate_id = aggregate.pk
    if not isinstance(aggregate_id, uuid.UUID):
        raise TypeError("outbox aggregates must have a UUID primary key")
    return OutboxEvent.objects.create(
        event_type=event_type,
        aggregate_type=aggregate._meta.label_lower,
        aggregate_id=aggregate_id,
        payload=payload or {},
    )


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(2**attempts, 300))


def dispatch_batch(limit: int | None = None) -> int:
    """Claim due rows with SKIP LOCKED, publish each as a Celery task, and mark it.

    Returns the number of rows claimed. A row sent but not committed is sent again
    later; tasks are idempotent, so a repeat is harmless.
    """
    limit = limit or settings.OUTBOX_BATCH_SIZE
    now = timezone.now()
    with transaction.atomic():
        rows = list(
            OutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(status=OutboxEvent.Status.PENDING, available_at__lte=now)
            .order_by("id")[:limit]
        )
        for row in rows:
            try:
                celery_app.send_task(
                    EVENT_TASKS[row.event_type],
                    kwargs=row.payload,
                    task_id=f"outbox-{row.pk}",
                )
            except Exception as exc:  # broker down, bad payload, ...
                row.attempts += 1
                row.available_at = now + _backoff(row.attempts)
                if row.attempts >= settings.OUTBOX_MAX_ATTEMPTS:
                    row.status = OutboxEvent.Status.FAILED
                log.warning("outbox.dispatch_failed", event_id=row.pk, attempts=row.attempts, error=str(exc))
                row.save(update_fields=["attempts", "available_at", "status"])
                continue
            row.status = OutboxEvent.Status.DISPATCHED
            row.dispatched_at = now
            row.save(update_fields=["status", "dispatched_at"])
    if rows:
        log.info("outbox.dispatched", claimed=len(rows))
    return len(rows)
