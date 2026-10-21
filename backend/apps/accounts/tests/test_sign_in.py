from datetime import timedelta

import pytest
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient

from apps.accounts.models import User, UserSession
from apps.evaluation.models import AuditEvent
from conftest import PASSWORD, code_for

LOGIN = "/api/v1/auth/login/"


def login(api, username, password=PASSWORD):
    return api.post(LOGIN, {"username": username, "password": password}, format="json")


def test_csrf_endpoint_sets_the_cookie(client):
    response = client.get("/api/v1/auth/csrf/")
    assert response.status_code == 204
    assert "csrftoken" in response.cookies


def test_sign_in_creates_a_session_row_and_an_audit_event(client, make_user):
    user = make_user()
    response = login(client, user.username)
    assert response.status_code == 200
    assert response.json()["mfa_required"] is False
    assert response.json()["user"]["username"] == user.username
    assert response.cookies["sessionid"]["httponly"]
    row = UserSession.objects.get(user=user)
    assert len(row.session_key_hash) == 64 and row.revoked_at is None
    assert AuditEvent.objects.filter(event_type="auth.login", actor_user=user).exists()
    assert client.get("/api/v1/auth/me/").json()["username"] == user.username


def test_wrong_password_and_unknown_user_get_the_same_answer(client, make_user):
    user = make_user()
    wrong = login(client, user.username, "not-the-password")
    unknown = login(client, "nobody-at-all", "not-the-password")
    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"] == "Invalid username or password."
    user.refresh_from_db()
    assert user.failed_login_count == 1


def test_five_failures_lock_the_account_and_an_admin_can_unlock_it(client, make_user, admin_client):
    user = make_user()
    statuses = [login(client, user.username, "bad-password").status_code for _ in range(5)]
    assert statuses[-1] == 423
    assert login(client, user.username).status_code == 423  # even the right password
    user.refresh_from_db()
    assert user.is_locked
    assert AuditEvent.objects.filter(event_type="auth.locked", entity_id=user.pk).exists()

    assert admin_client.post(f"/api/v1/admin/users/{user.pk}/unlock/").status_code == 200
    assert login(APIClient(), user.username).status_code == 200


def test_inactive_users_cannot_sign_in(client, make_user):
    user = make_user()
    User.objects.filter(pk=user.pk).update(is_active=False)
    assert login(client, user.username).status_code == 400


def test_sign_in_needs_a_csrf_token(csrf_client, make_user):
    user = make_user()
    response = login(csrf_client, user.username)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
    csrf_client.get("/api/v1/auth/csrf/")
    token = csrf_client.cookies["csrftoken"].value
    ok = csrf_client.post(LOGIN, {"username": user.username, "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=token)
    assert ok.status_code == 200


def test_writes_without_x_csrftoken_are_refused(csrf_client, make_user):
    user = make_user()
    csrf_client.get("/api/v1/auth/csrf/")
    token = csrf_client.cookies["csrftoken"].value
    csrf_client.post(LOGIN, {"username": user.username, "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=token)
    response = csrf_client.post("/api/v1/auth/logout/")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_sign_out_ends_the_session(signed_in):
    api, user = signed_in()
    assert api.post("/api/v1/auth/logout/").status_code == 204
    assert api.get("/api/v1/auth/me/").status_code == 401
    assert UserSession.objects.get(user=user).revoked_at is not None


@pytest.mark.parametrize(
    "change",
    [
        {"revoked_at": timezone.now()},
        {"expires_at": timezone.now() - timedelta(seconds=1)},
        {"last_seen_at": timezone.now() - timedelta(minutes=31)},
    ],
    ids=["revoked", "absolute-timeout", "idle-timeout"],
)
def test_ended_sessions_get_401_on_the_next_request(signed_in, change):
    api, user = signed_in()
    UserSession.objects.filter(user=user).update(**change)
    response = api.get("/api/v1/auth/me/")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "session_expired"
    assert api.get("/api/v1/auth/me/").status_code == 401


def test_sign_out_everywhere_revokes_every_session(make_user):
    user = make_user()
    first, second = APIClient(), APIClient()
    login(first, user.username)
    login(second, user.username)
    assert first.post("/api/v1/auth/sessions/revoke-all/").status_code == 204
    assert second.get("/api/v1/auth/me/").status_code == 401


class TestMfa:
    def test_a_user_with_an_app_must_enter_a_code(self, client, make_user):
        user = make_user()
        device = TOTPDevice.objects.create(user=user, name="authenticator", confirmed=True)
        response = login(client, user.username)
        assert response.json()["mfa_required"] is True
        assert client.get("/api/v1/auth/me/").json()["mfa_required"] is True
        blocked = client.get("/api/v1/auth/sessions/")
        assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "mfa_required"

        assert client.post("/api/v1/auth/mfa/verify/", {"code": "000000"}, format="json").status_code == 400
        assert client.post("/api/v1/auth/mfa/verify/", {"code": code_for(device)}, format="json").status_code == 200
        assert client.get("/api/v1/auth/sessions/").status_code == 200

    def test_set_up_and_confirm_an_authenticator_app(self, signed_in):
        api, user = signed_in()
        setup = api.post("/api/v1/auth/mfa/setup/").json()
        assert setup["otpauth_url"].startswith("otpauth://totp/") and setup["qr_svg"].startswith("<")
        device = TOTPDevice.objects.get(user=user, confirmed=False)
        assert api.post("/api/v1/auth/mfa/confirm/", {"code": code_for(device)}, format="json").status_code == 200
        user.refresh_from_db()
        assert user.mfa_enabled
        assert TOTPDevice.objects.get(user=user).confirmed

    def test_admins_need_only_a_password_by_default(self, signed_in):
        api, _ = signed_in("Admin")
        assert api.get("/api/v1/auth/me/").json()["mfa_setup_required"] is False
        assert api.get("/api/v1/admin/users/").status_code == 200

    def test_admin_pages_need_mfa_when_the_setting_is_on(self, signed_in, settings):
        settings.MFA_REQUIRED_FOR_ADMINS = True
        api, _ = signed_in("Admin")
        assert api.get("/api/v1/auth/me/").json()["mfa_setup_required"] is True
        response = api.get("/api/v1/admin/users/")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "mfa_required"


class TestPassword:
    def test_wrong_current_password_is_refused(self, signed_in):
        api, _ = signed_in()
        response = api.post(
            "/api/v1/auth/password/", {"old_password": "nope", "new_password": "a-brand-new-passphrase"}, format="json"
        )
        assert response.status_code == 400
        assert "old_password" in response.json()["error"]["details"]

    def test_changing_the_password_signs_out_other_sessions(self, make_user):
        user = make_user()
        here, elsewhere = APIClient(), APIClient()
        login(here, user.username)
        login(elsewhere, user.username)
        response = here.post(
            "/api/v1/auth/password/", {"old_password": PASSWORD, "new_password": "a-brand-new-passphrase"}, format="json"
        )
        assert response.status_code == 204
        assert here.get("/api/v1/auth/me/").status_code == 200
        assert elsewhere.get("/api/v1/auth/me/").status_code == 401
        assert login(APIClient(), user.username, "a-brand-new-passphrase").status_code == 200
