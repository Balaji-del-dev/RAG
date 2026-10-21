import pytest
from django.db import DatabaseError, transaction

from apps.core import audit
from apps.evaluation.models import AuditEvent
from apps.registry.models import PipelineVersion


def test_the_audit_log_cannot_be_changed_or_deleted(make_user):
    audit.record("test.event", actor=make_user())
    event = AuditEvent.objects.get(event_type="test.event")
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).update(event_type="rewritten")
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).delete()
    assert AuditEvent.objects.get(pk=event.pk).event_type == "test.event"


def test_a_published_pipeline_version_is_frozen_but_can_retire(db):
    version = PipelineVersion.objects.get(version_number=1)
    PipelineVersion.objects.filter(pk=version.pk).update(status="PUBLISHED")
    with pytest.raises(DatabaseError), transaction.atomic():
        PipelineVersion.objects.filter(pk=version.pk).update(config_json={"changed": True})
    with pytest.raises(DatabaseError), transaction.atomic():
        PipelineVersion.objects.filter(pk=version.pk).update(status="DRAFT")
    PipelineVersion.objects.filter(pk=version.pk).update(status="RETIRED")
    PipelineVersion.objects.filter(pk=version.pk).update(status="PUBLISHED")  # rollback
    assert PipelineVersion.objects.get(pk=version.pk).status == "PUBLISHED"
