import uuid

from django.db import models
from django.utils import timezone


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OutboxEvent(models.Model):
    """An event to hand to Celery, written in the same transaction as the change it announces."""

    class Status(models.TextChoices):
        PENDING = "PENDING"
        DISPATCHED = "DISPATCHED"
        FAILED = "FAILED"

    id = models.BigAutoField(primary_key=True)
    event_type = models.CharField(max_length=60)
    aggregate_type = models.CharField(max_length=60)
    aggregate_id = models.UUIDField()
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "outbox_events"
        indexes = [
            models.Index(
                fields=["available_at"],
                condition=models.Q(status="PENDING"),
                name="outbox_pending_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["PENDING", "DISPATCHED", "FAILED"]),
                name="outbox_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} {self.aggregate_type}:{self.aggregate_id} ({self.status})"


def choices_check(field: str, choices: type[models.TextChoices], name: str) -> models.CheckConstraint:
    """A database CHECK that a status/enum column holds only its TextChoices values."""
    return models.CheckConstraint(condition=models.Q(**{f"{field}__in": choices.values}), name=name)
