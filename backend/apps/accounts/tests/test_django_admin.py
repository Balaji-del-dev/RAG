import pytest
from django.test import Client

from apps.accounts.models import AccessGroup, DocumentAccessGrant, Role, User
from apps.core.models import OutboxEvent
from apps.documents.models import Document, DocumentVersion
from apps.evaluation.models import AuditEvent
from apps.registry.models import PipelineVersion
from conftest import PASSWORD


def admin_login(client, username):
    return client.post(
        "/django-admin/login/?next=/django-admin/",
        {"username": username, "password": PASSWORD, "next": "/django-admin/"},
    )


def test_the_admin_role_signs_in_with_username_and_password(make_user):
    user = make_user("Admin")
    assert not user.is_staff and not user.is_superuser
    client = Client()
    response = admin_login(client, user.username)
    assert response.status_code == 302 and response["Location"] == "/django-admin/"
    index = client.get("/django-admin/")
    assert index.status_code == 200
    assert b"Users" in index.content and b"Access groups" in index.content
    assert client.get("/django-admin/accounts/user/").status_code == 200


def test_other_roles_cannot_use_django_admin(make_user):
    user = make_user("Knowledge manager")
    client = Client()
    response = admin_login(client, user.username)
    assert response.status_code == 200  # the form again, with an error
    assert b"Please enter the correct" in response.content
    assert client.get("/django-admin/").status_code == 302  # back to the login page


def test_the_admin_css_is_served_in_local_debug_mode():
    from django.contrib.staticfiles import finders

    assert finders.find("admin/css/base.css")


# ---- add, change and delete for the Admin role


@pytest.fixture
def django_admin(make_user):
    user = make_user("Admin", username="boss")
    client = Client()
    assert admin_login(client, "boss").status_code == 302
    client.user = user
    return client


def admin_url(model, action="add", pk=None):
    base = f"/django-admin/{model._meta.app_label}/{model._meta.model_name}/"
    return base + (f"{pk}/{action}/" if pk else f"{action}/")


def test_every_table_of_ours_can_be_added_to_except_the_audit_log(django_admin):
    from django.contrib import admin

    ours = [m for m in admin.site._registry if m.__module__.startswith("apps.")]
    assert len(ours) >= 40
    for model in ours:
        expected = 403 if model is AuditEvent else 200
        assert django_admin.get(admin_url(model)).status_code == expected, model.__name__


def test_changes_made_in_django_admin_are_audited(django_admin):
    group = AccessGroup.objects.create(name="finance")
    response = django_admin.post(
        admin_url(AccessGroup, "change", group.pk),
        {"name": "finance-team", "description": "", "created_at_0": "2026-10-21", "created_at_1": "10:00:00"},
    )
    assert response.status_code == 302, response.content[:2000]
    group.refresh_from_db()
    assert group.name == "finance-team"
    event = AuditEvent.objects.get(event_type="django_admin.changed", entity_id=group.pk)
    assert event.actor == "boss" and "name" in event.details_json["fields"]


def test_adding_a_person_in_django_admin_sets_a_password_and_the_defaults(django_admin):
    response = django_admin.post(
        admin_url(User),
        {"username": "newbie", "email": "newbie@example.org", "display_name": "New Bie", "usable_password": "true",
         "password1": PASSWORD, "password2": PASSWORD},
    )  # fmt: skip
    assert response.status_code == 302, response.content[:2000]
    user = User.objects.get(username="newbie")
    assert user.check_password(PASSWORD)
    assert list(user.user_roles.values_list("role__name", flat=True)) == [Role.USER]
    assert list(user.user_access_groups.values_list("access_group__name", flat=True)) == [AccessGroup.GENERAL]


def test_the_last_active_admin_cannot_be_deleted(django_admin):
    assert django_admin.get(admin_url(User, "delete", django_admin.user.pk)).status_code == 403


def test_deleting_a_document_in_django_admin_works_like_the_console(django_admin):
    document = Document.objects.create(filename="old.pdf", file_extension="pdf", mime_type="application/pdf",
                                       created_by=django_admin.user)  # fmt: skip
    DocumentVersion.objects.create(document=document, version_number=1, content_sha256="0" * 64, file_size=1,
                                   storage_bucket="documents", storage_object_key="k")  # fmt: skip
    response = django_admin.post(admin_url(Document, "delete", document.pk), {"post": "yes"})
    assert response.status_code == 302
    document.refresh_from_db()
    assert document.deleted_at is not None and document.lifecycle_status == Document.Lifecycle.DELETED
    assert OutboxEvent.objects.filter(event_type="index.delete").count() == 1


def test_changing_access_grants_in_django_admin_updates_the_search_indexes(django_admin):
    document = Document.objects.create(filename="a.pdf", file_extension="pdf", mime_type="application/pdf",
                                       created_by=django_admin.user)  # fmt: skip
    grant = DocumentAccessGrant.objects.create(document=document, access_group=AccessGroup.objects.get(name="general"))
    assert django_admin.post(admin_url(DocumentAccessGrant, "delete", grant.pk), {"post": "yes"}).status_code == 302
    assert OutboxEvent.objects.filter(event_type="index.acl", aggregate_id=document.pk).count() == 1


def test_a_published_pipeline_version_is_view_only_but_a_draft_is_editable(django_admin):
    published = PipelineVersion.objects.get(pipeline__name="default", version_number=1)
    PipelineVersion.objects.filter(pk=published.pk).update(status=PipelineVersion.Status.PUBLISHED)
    page = django_admin.get(admin_url(PipelineVersion, "change", published.pk))
    assert page.status_code == 200 and b'name="_save"' not in page.content
    assert django_admin.get(admin_url(PipelineVersion, "delete", published.pk)).status_code == 403

    from apps.registry import services as registry

    draft = registry.clone_version(PipelineVersion.objects.get(pk=published.pk), by=django_admin.user)
    assert b'name="_save"' in django_admin.get(admin_url(PipelineVersion, "change", draft.pk)).content
