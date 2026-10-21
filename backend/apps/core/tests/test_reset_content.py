import pytest
from django.core.management import call_command

from apps.accounts.models import AccessGroup, User
from apps.core.management.commands import reset_content
from apps.documents.models import Document
from apps.evaluation.models import AuditEvent
from apps.registry.models import PipelineVersion


@pytest.fixture
def no_real_services(monkeypatch):
    """Never touch the real MinIO buckets or indexes from a test."""
    calls = []
    monkeypatch.setattr(reset_content.storage, "remove_prefix", lambda bucket, prefix: calls.append(bucket) or 0)
    monkeypatch.setattr(reset_content.vector_store, "drop", calls.append)
    monkeypatch.setattr(reset_content.search_index, "drop", calls.append)
    return calls


def test_no_kept_table_points_into_the_content_tables():
    assert reset_content.outside_references(reset_content.content_models()) == []


def test_dry_run_removes_nothing(make_user, no_real_services):
    user = make_user()
    Document.objects.create(filename="a.pdf", file_extension="pdf", mime_type="application/pdf", created_by=user)
    call_command("reset_content")
    assert Document.objects.count() == 1 and no_real_services == []


def test_reset_removes_content_and_keeps_accounts_and_pipelines(make_user, no_real_services):
    user = make_user()
    Document.objects.create(filename="a.pdf", file_extension="pdf", mime_type="application/pdf", created_by=user)
    call_command("reset_content", "--yes")
    assert Document.objects.count() == 0
    assert User.objects.filter(pk=user.pk).exists() and AccessGroup.objects.filter(name="general").exists()
    assert PipelineVersion.objects.exists()
    assert AuditEvent.objects.filter(event_type="content.reset").exists()
    assert set(no_real_services) == {"rag-originals", "rag-artifacts"}
