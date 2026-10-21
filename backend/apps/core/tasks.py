import structlog
from celery import shared_task

log = structlog.get_logger(__name__)


@shared_task(name="core.ping")
def ping(**payload) -> str:
    """Test task: proves the outbox -> Redis -> Celery path works."""
    log.info("core.ping", payload=payload)
    return "pong"


@shared_task(name="core.purge_dispatched_outbox")
def purge_dispatched_outbox(keep_days: int = 7) -> int:
    """Daily: delete outbox rows that were delivered more than keep_days ago."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import OutboxEvent

    cutoff = timezone.now() - timedelta(days=keep_days)
    deleted, _ = OutboxEvent.objects.filter(status=OutboxEvent.Status.DISPATCHED, dispatched_at__lt=cutoff).delete()
    return deleted
