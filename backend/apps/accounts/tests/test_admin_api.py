from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient

from apps.accounts.models import AccessGroup, Role, User, UserSession
from apps.evaluation.models import AuditEvent
from conftest import PASSWORD


def role_id(name):
    return str(Role.objects.get(name=name).pk)


def test_create_user_adds_the_user_role_and_audits_it(admin_client):
    response = admin_client.post(
        "/api/v1/admin/users/",
        {"username": "kim", "email": "kim@example.org", "password": "a-long-enough-password", "role_ids": [role_id("Evaluator")]},
        format="json",
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert {r["name"] for r in body["roles"]} == {"User", "Evaluator"}
    assert [g["name"] for g in body["access_groups"]] == ["general"]
    assert AuditEvent.objects.filter(event_type="user.created", actor_user=admin_client.user).exists()
    assert (
        APIClient()
        .post("/api/v1/auth/login/", {"username": "kim", "password": "a-long-enough-password"}, format="json")
        .status_code
        == 200
    )


def test_create_user_validates_fields(admin_client, make_user):
    make_user(username="taken")
    response = admin_client.post(
        "/api/v1/admin/users/", {"username": "taken", "email": "bad", "password": "short"}, format="json"
    )
    assert response.status_code == 400
    details = response.json()["error"]["details"]
    assert "username" in details and "email" in details


def test_list_users_can_search_and_filter(admin_client, make_user):
    make_user("Evaluator", username="eva")
    make_user(username="bob")
    names = [u["username"] for u in admin_client.get("/api/v1/admin/users/?role=Evaluator").json()["results"]]
    assert "eva" in names and "bob" not in names  # svc-evaluation is an Evaluator too
    assert [u["username"] for u in admin_client.get("/api/v1/admin/users/?search=bo").json()["results"]] == ["bob"]


def test_set_roles_keeps_the_user_role(admin_client, make_user):
    user = make_user("Evaluator")
    response = admin_client.put(f"/api/v1/admin/users/{user.pk}/roles/", {"ids": [role_id("Knowledge manager")]}, format="json")
    assert response.status_code == 200
    assert {r["name"] for r in response.json()["roles"]} == {"User", "Knowledge manager"}


def test_the_last_admin_cannot_be_demoted_or_disabled(admin_client):
    me = admin_client.user
    demote = admin_client.put(f"/api/v1/admin/users/{me.pk}/roles/", {"ids": []}, format="json")
    assert demote.status_code == 409
    disable = admin_client.patch(f"/api/v1/admin/users/{me.pk}/", {"is_active": False}, format="json")
    assert disable.status_code == 409


def test_disabling_a_user_signs_them_out(admin_client, signed_in):
    api, user = signed_in()
    assert admin_client.patch(f"/api/v1/admin/users/{user.pk}/", {"is_active": False}, format="json").status_code == 200
    assert api.get("/api/v1/auth/me/").status_code == 401
    assert not UserSession.objects.filter(user=user, revoked_at__isnull=True).exists()


def test_set_access_groups(admin_client, make_user):
    user = make_user()
    finance = AccessGroup.objects.create(name="finance")
    response = admin_client.put(f"/api/v1/admin/users/{user.pk}/access-groups/", {"ids": [str(finance.pk)]}, format="json")
    assert [g["name"] for g in response.json()["access_groups"]] == ["finance"]


def test_reset_mfa_removes_the_app_and_ends_sessions(admin_client, signed_in):
    api, user = signed_in()
    TOTPDevice.objects.create(user=user, name="authenticator", confirmed=True)
    User.objects.filter(pk=user.pk).update(mfa_enabled=True)
    assert admin_client.post(f"/api/v1/admin/users/{user.pk}/reset-mfa/").json()["mfa_enabled"] is False
    assert not TOTPDevice.objects.filter(user=user).exists()
    assert api.get("/api/v1/auth/me/").status_code == 401


def test_access_groups_crud_and_the_general_group_is_protected(admin_client):
    created = admin_client.post("/api/v1/admin/access-groups/", {"name": "legal", "description": "Legal team"}, format="json")
    assert created.status_code == 201
    group_id = created.json()["id"]
    assert (
        admin_client.patch(f"/api/v1/admin/access-groups/{group_id}/", {"description": "Legal"}, format="json").status_code == 200
    )
    assert admin_client.delete(f"/api/v1/admin/access-groups/{group_id}/").status_code == 204
    general = AccessGroup.objects.get(name="general")
    assert admin_client.delete(f"/api/v1/admin/access-groups/{general.pk}/").status_code == 409


def test_admin_can_list_and_revoke_sessions(admin_client, signed_in):
    api, user = signed_in()
    rows = admin_client.get(f"/api/v1/admin/sessions/?user={user.username}").json()["results"]
    assert len(rows) == 1 and rows[0]["username"] == user.username
    assert admin_client.post(f"/api/v1/admin/sessions/{rows[0]['id']}/revoke/").status_code == 204
    assert api.get("/api/v1/auth/me/").status_code == 401
    assert AuditEvent.objects.filter(event_type="session.revoked", entity_id=user.pk).exists()


def test_bootstrap_admin_creates_an_admin_with_mfa(db, monkeypatch, capsys):
    from django.core.management import call_command

    monkeypatch.setenv("BOOT_PW", PASSWORD)
    call_command("bootstrap_admin", username="root-admin", email="root@example.org", password_env="BOOT_PW")
    user = User.objects.get(username="root-admin")
    assert user.has_perm("accounts.manage") and user.mfa_enabled
    assert TOTPDevice.objects.filter(user=user, confirmed=True).exists()
